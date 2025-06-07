# word_quiz.py

import csv

def load_quiz_questions(filename="word_quiz_500.csv"):
    questions = []
    with open(filename, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            questions.append({
                "word": row["word"],
                "option_a": row["option_a"],
                "option_b": row["option_b"],
                "option_c": row["option_c"],
                "correct": row["correct"]
            })
    return questions
