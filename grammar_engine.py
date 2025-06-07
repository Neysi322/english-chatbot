import csv
import random

def load_grammar_tasks_by_level(level):
    tasks = []
    with open("grammar_tasks.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["level"].strip().upper() == level.strip().upper():
                tasks.append(row)
    return tasks

def check_grammar_answer(user_answer, correct_answer):
    return user_answer.strip().lower() == correct_answer.strip().lower()
