from flask import Flask, render_template, request, jsonify
import os
import json
import csv
import subprocess
import whisper
import re
import time
import pandas as pd
from fuzzywuzzy import process, fuzz  # Narzędzie do fuzzy matching

# Utwórz aplikację Flask
app = Flask(__name__)

# Ścieżki do plików
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

app.template_folder = TEMPLATES_DIR
app.static_folder = STATIC_DIR

# Globalne ładowanie modelu Whisper
model = whisper.load_model("small")  # Możesz wybrać "tiny", "small", "medium", "large"

# Lista oczekiwanych odpowiedzi
valid_responses = ["Niemal codziennie", "Kilka dni", "Więcej niż połowę dnia", "Wcale nie dokuczały"]
response_to_score = {
    "Wcale nie dokuczały": 0,
    "Kilka dni": 1,
    "Więcej niż połowę dnia": 2,
    "Niemal codziennie": 3
}

# Słownik zamienników dla znanych błędów
corrections = {
    "Cały nie dokuczały": "Wcale nie dokuczały",
    "Całe nie dokuczały": "Wcale nie dokuczały",
    "Wspaniale nie dokuczały": "Wcale nie dokuczały",
    "Więcej niz połowę dnia": "Więcej niż połowę dnia",
    "Powodnia": "Więcej niż połowę dnia"  # Dla błędnych fraz generowanych przez Whisper
}

# Funkcja do dopasowania i poprawy odpowiedzi
# Funkcja do czyszczenia odpowiedzi
def clean_transcription(response, valid_responses):
    for valid_response in valid_responses:
        if valid_response.lower() in response.lower():
            return valid_response  # Zwraca poprawną frazę
    return response  # Zwraca oryginalną odpowiedź, jeśli brak pasującej frazy

# Funkcja dopasowania i czyszczenia
def find_closest_match(response, valid_responses, corrections):
    response = response.rstrip('.').strip()

    # 1. Sprawdź w słowniku zamienników
    if response in corrections:
        return corrections[response]
    import csv
    # 2. Fuzzy matching
    match = process.extractOne(response, valid_responses, scorer=fuzz.ratio)
    if match:
        # 3. Usuń zbędne słowa wokół frazy
        return clean_transcription(match[0], valid_responses)
    return response


def calculate_phq_score(csv_path):
    score = 0
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    for _, row in df.iterrows():
        print(row)
        if not any(keyword in row["Pytanie"] for keyword in ["Wiek", "Płeć", "Nastrój"]):
            response = row["Odpowiedź"].strip().rstrip('.')
            matched_response = find_closest_match(response, valid_responses, corrections)
            score += response_to_score.get(matched_response, 0)
    return score

@app.route("/", methods=["GET", "POST"])
def home():
    if os.path.exists(csv_path):
        os.remove(csv_path)
        print(f"Usunięto istniejący plik: {csv_path}")
    if request.method == "POST":
        age = request.form.get("age")
        gender = request.form.get("gender")
        data = {"age": age, "gender": gender}

        # Zapisz dane ankiety
        survey_file = os.path.join(DATA_DIR, "survey_data.json")
        with open(survey_file, "w") as file:
            json.dump(data, file)

        return jsonify({"message": "Wyniki ankiety zostały przesłane do hosta"}), 200

    return render_template("survey.html")


@app.route("/summary")
def summary_page():
    csv_path = os.path.join(DATA_DIR, "transcriptions.csv")
    max_wait_time = 5
    start_time = time.time()

    while time.time() - start_time < max_wait_time:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        total_responses = df.shape[0]

        required_responses = 9 + 3 # Liczba pytań PHQ + "Wiek", "Płeć" i "Nastrój"
        if total_responses >= required_responses:
            break
        time.sleep(0.5)


    phq_score = calculate_phq_score(csv_path)

    if phq_score <= 4:
        severity = "Brak depresji"
    elif phq_score <= 9:
        severity = "Łagodna depresja"
    elif phq_score <= 14:
        severity = "Umiarkowana depresja"
    elif phq_score <= 19:
        severity = "Umiarkowanie ciężka depresja"
    else:
        severity = "Ciężka depresja"

    responses = []
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        for _, row in df.iterrows():
            question = row["Pytanie"]
            if any(keyword in question for keyword in ["Wiek", "Płeć", "Nastrój"]):
                continue
            response = row["Odpowiedź"].strip().rstrip('.')
            matched_response = find_closest_match(response, valid_responses, corrections)
            points = response_to_score.get(matched_response, 0)
            responses.append({"Pytanie": question, "Odpowiedź": matched_response, "Punkty": points})

    return render_template("summary.html", phq_score=phq_score, severity=severity, responses=responses)

    return render_template("summary.html", phq_score=phq_score, severity=severity)

@app.route("/test", methods=["GET", "POST"])
def test_page():
    csv_path = os.path.join(DATA_DIR, "transcriptions.csv")
    if request.method == "POST":
        # Pobierz dane z formularza
        age = request.form.get("age")
        gender = request.form.get("gender")
        mood = request.form.get("mood")

        # Jeśli plik nie istnieje, utwórz go i dodaj nagłówki
        if not os.path.exists(csv_path):
            with open(csv_path, mode="w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=["Pytanie", "Odpowiedź"])
                writer.writeheader()

        # Dodaj dane ankiety do pliku CSV
        with open(csv_path, mode="a", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=["Pytanie", "Odpowiedź"])
            writer.writerow({"Pytanie": "Wiek:", "Odpowiedź": age})
            writer.writerow({"Pytanie": "Płeć:", "Odpowiedź": gender})
            writer.writerow({"Pytanie": "Nastrój:", "Odpowiedź": mood})

        # Przekierowanie lub renderowanie strony po przesłaniu danych
        return render_template("test.html")

    return render_template("test.html")


@app.route("/test/start")
def start_test():
    return render_template("voice_test.html")

@app.route("/upload_audio", methods=["POST"])
def upload_audio():
    file = request.files.get("audio_file")
    question = request.form.get("question", "Nieznane pytanie")
    if file:
        try:
            # Ścieżki do plików audio
            audio_path = os.path.join(DATA_DIR, "test_audio.webm")
            processed_audio_path = os.path.join(DATA_DIR, "processed_audio.wav")
            csv_path = os.path.join(DATA_DIR, "transcriptions.csv")

            # Zapisz plik audio
            file.save(audio_path)

            # Popraw jakość audio za pomocą FFmpeg
            command_process_audio = [
                r"C:\ffmpeg\bin\ffmpeg.exe",
                "-y",
                "-i", audio_path,
                "-af", "highpass=f=200, lowpass=f=3000, loudnorm, silenceremove=1:0:-50dB",
                "-ar", "16000",
                "-ac", "1",
                processed_audio_path
            ]
            subprocess.run(command_process_audio, check=True)

            # Transkrypcja za pomocą Whisper
            result = model.transcribe(
                processed_audio_path,
                language="pl",
                initial_prompt="Nagranie zawiera odpowiedzi. Odpowiedzi powinny być zgodne z listą: 'Niemal codziennie', 'Kilka dni', 'Więcej niż połowę dnia', 'Wcale nie dokuczały'. Proszę transkrybować dokładnie w tym formacie.",
                temperature=0.0
            )
            transcription = result["text"]
            corrected_response = find_closest_match(transcription, valid_responses, corrections)

            # Wczytaj istniejące dane z CSV, jeśli plik istnieje
            rows = []
            if os.path.isfile(csv_path):
                with open(csv_path, mode="r", encoding="utf-8-sig") as csv_file:
                    reader = csv.DictReader(csv_file)
                    rows = list(reader)

            # Sprawdź, czy pytanie już istnieje w pliku, i zaktualizuj lub dodaj odpowiedź
            updated = False
            for row in rows:
                if row["Pytanie"] == question:
                    row["Odpowiedź"] = corrected_response
                    updated = True
                    break

            if not updated:
                rows.append({"Pytanie": question, "Odpowiedź": corrected_response})

            # Zapisz dane do pliku CSV
            with open(csv_path, mode="w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=["Pytanie", "Odpowiedź"])
                writer.writeheader()
                writer.writerows(rows)

            return jsonify({
                "message": "Plik audio został przetworzony!",
                "transcription": transcription,
                "corrected_response": corrected_response
            }), 200

        except subprocess.CalledProcessError as e:
            return jsonify({"error": f"Konwersja FFmpeg nie powiodła się: {e}"}), 400
        except Exception as e:
            return jsonify({"error": f"Nie udało się przetworzyć pliku audio. {e}"}), 400

    return jsonify({"error": "Nie otrzymano pliku audio."}), 400


if __name__ == "__main__":
    # Ścieżka do pliku CSV
    csv_path = os.path.join(DATA_DIR, "transcriptions.csv")



    app.run(host="0.0.0.0", port=8080, debug=True)