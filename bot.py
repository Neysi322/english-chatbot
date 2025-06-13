import logging
import os
import pyttsx3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputFile
from aiogram.utils import executor
from mistral_client import ask_mistral
from whisper_transcriber import transcribe
from test_engine import load_all_questions, evaluate_answer

from gtts import gTTS
import csv
import random
import re
import json



API_TOKEN = '7958579468:AAF3d-BnWMxwt8ct0LNlWdBQaR16-Wy0JvM' 


USER_RESULTS_FILE = "user_results.json"
user_results = {}

def load_user_results():
    global user_results
    if os.path.exists(USER_RESULTS_FILE):
        with open(USER_RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Преобразуем ключи обратно в int
            user_results = {int(k): v for k, v in data.items()}
        print("✅ Загруженные результаты:", user_results)
    else:
        user_results = {}
        print("⚠️ Файл результатов не найден, создаю пустой.")


load_user_results()  



dialog_state = {}  
user_language = {}  

speak_sessions = {}  

translation_mode = {}  

active_mode = {}  # uid -> "speaking", "reading", "conversation", ...






logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

reading_data = []
with open("reading_texts.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    reading_data = list(reader)

reading_sessions = {}  


@dp.message_handler(lambda msg: msg.from_user.id in reading_sessions, content_types=types.ContentType.VOICE)
async def handle_reading_response(message: types.Message):
    uid = message.from_user.id
    lang = user_language.get(uid, "en")
    session = reading_sessions[uid]
    current_text = session["texts"][session["current"]]

    
    file_info = await bot.get_file(message.voice.file_id)
    await bot.download_file(file_info.file_path, "user_reading.ogg")
    os.system("ffmpeg -y -i user_reading.ogg -ar 16000 -ac 1 user_reading.wav")

    await message.answer("🕵️‍♂️ Анализируем твоё произношение..." if lang == "en" else "🕵️‍♂️ 발음을 분석 중입니다...")

    recognized = transcribe("user_reading.wav", lang=lang).strip()

    def normalize(text):
        text = text.lower()
        text = re.sub(r"[^\w\s']", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    if normalize(recognized) == normalize(current_text):
        await message.answer("✅ Отлично прочитано!" if lang == "en" else "✅ 아주 잘 읽었어요!")
    else:
        await message.answer(
            f"❌ Распознано: *{recognized}*\n✅ Ожидалось: *{current_text}*"
            if lang == "en" else
            f"❌ 인식된 문장: *{recognized}*\n✅ 정답: *{current_text}*",
            parse_mode="Markdown"
        )

    session["current"] += 1
    await send_reading_text(message, uid)



listening_data = []
with open("listening_words.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    listening_data = list(reader)


listening_sessions = {}  

@dp.message_handler(lambda msg: msg.text == "🎧 Pronunciation")
async def handle_listening_start(message: types.Message):
    translation_mode[message.from_user.id] = False

    uid = message.from_user.id
    words = random.sample(listening_data, min(1000, len(listening_data)))  

    listening_sessions[uid] = {
        "words": words,
        "current": 0,
        "score": 0,
        "target": ""
    }

    await message.answer("🎧 Запуск режима Pronunciation! Слушай и пиши услышанное.", reply_markup=stop_kb)

    await send_listening_word(message, uid)

@dp.message_handler(lambda msg: msg.text in ["⛔ Стоп", "⛔ 정지"])
async def handle_stop(message: types.Message):
    uid = message.from_user.id
    dialog_state.pop(uid, None)
    user_data.pop(uid, None)
    listening_sessions.pop(uid, None)

    lang = user_language.get(uid, "en")
    kb = main_kb_en if lang == "en" else main_kb_ko
    await message.answer("⛔ Режим остановлен. Возвращаюсь в меню.", reply_markup=kb)
    


async def send_listening_word(message, uid):
    session = listening_sessions[uid]
    index = session["current"]

    if index >= 100:  
        score = session["score"]
        total = index  
        del listening_sessions[uid]
        await message.answer(f"🏁 Игра завершена!\n\n🎯 Верных ответов: {score} из {total}")
        return


    word = session["words"][index]["word"]
    session["target"] = word

    audio_file = f"listen_{uid}.wav"
    synthesize_speech(f"The word is, {word}.", audio_file, lang="en")

    with open(audio_file, "rb") as voice:
        await bot.send_voice(chat_id=message.chat.id, voice=voice)
    os.remove(audio_file)

    await message.answer(f"🔤 Вопрос {index+1}/100: Напиши слово, которое ты услышал.")



@dp.message_handler(lambda msg: msg.from_user.id in listening_sessions)
async def handle_listening_response(message: types.Message):
    uid = message.from_user.id
    session = listening_sessions[uid]
    target = session["target"].strip().lower()
    guess = message.text.strip().lower()

    if guess == target:
        session["score"] += 1
        await message.answer("✅ Верно!")
    else:
        await message.answer(f"❌ Неверно. Правильный ответ: *{target}*", parse_mode="Markdown")

    session["current"] += 1
    await send_listening_word(message, uid)

@dp.message_handler(commands=["language"])
async def choose_language(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🇬🇧 English"), KeyboardButton("🇰🇷 Korean"))
    await message.answer("🌐 Choose your language for conversation mode:", reply_markup=kb)

@dp.message_handler(lambda msg: msg.text in ["🇬🇧 English", "🇰🇷 Korean"])
async def set_language_and_show_menu(message: types.Message):
    uid = message.from_user.id
    lang = "en" if message.text == "🇬🇧 English" else "ko"
    user_language[uid] = lang

    if lang == "ko":
        await message.answer("✅ 언어가 *한국어*로 설정되었습니다.", parse_mode="Markdown", reply_markup=main_kb_ko)
    else:
        await message.answer("✅ Language set to *English*.", parse_mode="Markdown", reply_markup=main_kb_en)



def save_user_results():
    with open(USER_RESULTS_FILE, "w", encoding="utf-8") as f:
        # Преобразуем int-ключи в строки при сохранении
        json.dump({str(k): v for k, v in user_results.items()}, f, ensure_ascii=False, indent=2)







def synthesize_speech(text, filename, lang="en"):
    if lang in ["en", "ko"]:
        tts = gTTS(text=text, lang=lang)
        tts.save(filename)
    else:
        raise ValueError("Unsupported language for TTS")


@dp.message_handler(lambda msg: msg.from_user.id in dialog_state)
async def continue_conversation(message: types.Message):
    uid = message.from_user.id
    user_input = message.text.strip()


    if user_input in ["📊 Test", "🌐 Translater", "👤 Personal page", "💬 Speaking", "🎧 Pronunciation"]:
        dialog_state.pop(uid, None)
        lang = user_language.get(uid, "en")
        kb = main_kb_en if lang == "en" else main_kb_ko
        await message.answer("🛑 Вы прервали разговорный режим.", reply_markup=kb)

        return

    dialog_state[uid].append({"role": "user", "content": user_input})


    prompt = "\n".join([
        f"{'User' if entry['role'] == 'user' else 'AI'}: {entry['content']}"
        for entry in dialog_state[uid][-6:]
    ])
    prompt += "\nAI:"

    try:
        response_raw = ask_mistral(prompt)
        ai_response = response_raw.strip().split("\n")[0].removeprefix("AI:").strip()

     
        dialog_state[uid].append({"role": "assistant", "content": ai_response})


        await message.answer(f"🤖 {ai_response}")

  
  
        audio_path = f"response_{uid}.wav"
        synthesize_speech(ai_response, audio_path, lang=user_language.get(uid, "en"))
        with open(audio_path, "rb") as voice_file:
            await bot.send_voice(chat_id=message.chat.id, voice=voice_file)
        os.remove(audio_path)


    except Exception as e:
        await message.answer(f"⚠️ Ошибка генерации или синтеза: {e}")




main_kb_en = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb_en.add(KeyboardButton("🌐 Translater"), KeyboardButton("📝 Test"), KeyboardButton("👤 Personal page"), KeyboardButton("💬 Speaking"), KeyboardButton("🎧 Pronunciation"), KeyboardButton("🌍 Change language"), KeyboardButton("🗣 Listening"), KeyboardButton("📖 Reading")
)
main_kb_ko = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb_ko.add(
    KeyboardButton("💬 대화 모드"),
    KeyboardButton("🌐 번역기"),
    KeyboardButton("🌍 언어 변경"),
    KeyboardButton("🗣 따라 말하고 녹음하기"),
    KeyboardButton("📝 문법 테스트"),  
    KeyboardButton("📖 읽기 연습"),
    KeyboardButton("👤 내 정보") 
)
stop_kb = ReplyKeyboardMarkup(resize_keyboard=True)
stop_kb.add(KeyboardButton("⛔ Стоп"))


def synthesize_offline(text, filename):
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)  
    engine.setProperty('voice', 'english')  
    engine.save_to_file(text, filename)
    engine.runAndWait()






@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🇬🇧 English"), KeyboardButton("🇰🇷 Korean"))
    await message.answer("👋 Please choose your language / 언어를 선택하세요:", reply_markup=kb)


@dp.message_handler(lambda msg: msg.text in ["🌍 Change language", "🌍 언어 변경"])
async def choose_language(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🇬🇧 English"), KeyboardButton("🇰🇷 Korean"))
    await message.answer("🌐 Выберите язык / 언어를 선택하세요:", reply_markup=kb)




@dp.message_handler(lambda msg: msg.text in ["🗣 Listening", "🗣 따라 말하고 녹음하기"])
async def start_speak_task(message: types.Message):
    uid = message.from_user.id
    translation_mode[uid] = False

    print("🧪 Вызван start_speak_task")

    # Очистка всех других режимов для этого пользователя
    reading_sessions.pop(uid, None)
    dialog_state.pop(uid, None)
    user_data.pop(uid, None)
    listening_sessions.pop(uid, None)
    active_mode.pop(uid, None)
    
    if uid not in user_language:
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("🇬🇧 English"), KeyboardButton("🇰🇷 Korean"))
        await message.answer("❗️Пожалуйста, выберите язык:", reply_markup=kb)
        return

    lang = user_language[uid]

    filtered_phrases = [row["phrase"] for row in speak_data if row["lang"] == lang]
    if not filtered_phrases:
        await message.answer("😔 Нет доступных фраз для выбранного языка.")
        return

    random.shuffle(filtered_phrases)
    speak_sessions[uid] = {
        "phrases": filtered_phrases[:10],
        "current": 0
    }

    # Установка активного режима
    active_mode[uid] = "speaking"

    await message.answer(
        "🎙 Повторяй вслух и записывай голосовое сообщение!" if lang == "en"
        else "🎙 음성을 듣고 똑같이 말하세요!",
        reply_markup=stop_kb
    )

    await send_speak_phrase(message, uid)



async def send_speak_phrase(message, uid):
    session = speak_sessions[uid]
    index = session["current"]
    lang = user_language.get(uid, "en")

    if index >= len(session["phrases"]):
        del speak_sessions[uid]
        await message.answer("✅ Задание завершено!" if lang == "en" else "✅ 연습이 완료되었습니다!")
        return

    phrase = session["phrases"][index]
    audio_path = f"speak_{uid}.mp3"

    try:
        tts = gTTS(text=phrase, lang=lang)
        tts.save(audio_path)

        with open(audio_path, "rb") as voice_file:
            await bot.send_voice(chat_id=message.chat.id, voice=voice_file)
        os.remove(audio_path)

        await message.answer(f"🗣 Скажи: *{phrase}*" if lang == "en" else f"🗣 말해보세요: *{phrase}*", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка генерации речи: {e}")




@dp.message_handler(lambda msg: msg.text in ["📖 Reading", "📖 읽기 연습"])
async def start_reading(message: types.Message):
    translation_mode[message.from_user.id] = False

    uid = message.from_user.id
    lang = user_language.get(uid, "en")

 
    candidates = [row["text"] for row in reading_data if row["lang"] == lang]
    if not candidates:
        await message.answer("😔 Нет доступных текстов для чтения.")
        return

 
    reading_sessions[uid] = {
        "texts": random.sample(candidates, len(candidates)),
        "current": 0
    }

    await send_reading_text(message, uid)


async def send_reading_text(message, uid):
    session = reading_sessions[uid]
    lang = user_language.get(uid, "en")

    if session["current"] >= len(session["texts"]):
        del reading_sessions[uid]
        await message.answer("✅ Все тексты прочитаны!" if lang == "en" else "✅ 모든 텍스트를 다 읽었어요!")
        return

    current_text = session["texts"][session["current"]]
    await message.answer(
        f"📖 Прочитай вслух и отправь голосовое сообщение:\n\n*{current_text}*"
        if lang == "en" else
        f"📖 큰 소리로 읽고 음성 메시지를 보내세요:\n\n*{current_text}*",
        parse_mode="Markdown",
        reply_markup=stop_kb
    )




speak_data = []
with open("speak_phrases.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    reader.fieldnames = [name.strip().replace('\ufeff', '') for name in reader.fieldnames]
    
    for row in reader:
        if "lang" in row and "phrase" in row and row["lang"] and row["phrase"]:
            row["lang"] = row["lang"].strip().replace('\ufeff', '')
            row["phrase"] = row["phrase"].strip().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
            row["phrase"] = row["phrase"].replace("   ", "'").replace("  ", "'").replace("’", "'")
            row["phrase"] = row["phrase"].replace(" m ", "'m ").replace(" s ", "'s ").replace(" t ", "'t ")
            speak_data.append(row)

print(f"✅ Загружено {len(speak_data)} фраз.")
print(f"🌍 Доступные языки: {set(row['lang'] for row in speak_data)}")






@dp.message_handler(
    lambda msg: msg.from_user.id in speak_sessions and active_mode.get(msg.from_user.id) == "speaking",
    content_types=types.ContentType.VOICE
)
async def handle_speak_response(message: types.Message):
    print("🔊 handle_speak_response запущен")
    print(f"🗣 Пользователь: {message.from_user.id}")

    def normalize(text):
        text = text.lower()
        text = re.sub(r"[^\w\s']", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    uid = message.from_user.id
    session = speak_sessions[uid]
    lang = user_language.get(uid, "en")
    target_phrase = session["phrases"][session["current"]].strip()

    file_info = await bot.get_file(message.voice.file_id)
    await bot.download_file(file_info.file_path, "user_speak.ogg")
    os.system("ffmpeg -y -i user_speak.ogg -ar 16000 -ac 1 user_speak.wav")

    print("🎙️ Начинается распознавание речи...")
    print(f"🎯 Язык распознавания: {lang}")

    user_text = transcribe("user_speak.wav", lang=lang)

    print(f"📝 Распознанный текст: {user_text}")
    print(f"🎯 Ожидалось: {target_phrase}")

    if normalize(user_text) == normalize(target_phrase):
        await message.answer("✅ Отлично! Всё правильно!" if lang == "en" else "✅ 아주 잘했어요!")
    else:
        await message.answer(
            f"❌ Было сказано: *{user_text}*\n✅ Правильно: *{target_phrase}*"
            if lang == "en" else
            f"❌ 인식된 문장: *{user_text}*\n✅ 정답: *{target_phrase}*",
            parse_mode="Markdown"
        )

    session["current"] += 1
    await send_speak_phrase(message, uid)






@dp.message_handler(lambda msg: msg.text in ["💬 대화 모드", "💬 Speaking"])

async def start_conversation_mode(message: types.Message):
    translation_mode[message.from_user.id] = False

    uid = message.from_user.id
    active_mode[uid] = "conversation"
    
    dialog_state.pop(uid, None)
    user_data.pop(uid, None)

    lang = user_language.get(uid, "en")

    if lang == "ko":
        dialog_state[uid] = [
            {"role": "system", "content": "당신은 한국어로 친근하게 대화하는 연습 상대입니다. 대화를 자연스럽고 간단하게 유지하세요."},
            {"role": "assistant", "content": "안녕하세요! 오늘 기분이 어때요?"}
        ]
        await message.answer("💬 한국어로 대화를 시작합니다:\n\n🤖 *안녕하세요! 오늘 기분이 어때요?*", parse_mode="Markdown", reply_markup=stop_kb)

    else:
        dialog_state[uid] = [
            {"role": "system", "content": "You are a friendly English-speaking partner for conversation practice. Keep the dialog simple and natural."},
            {"role": "assistant", "content": "Hi there! How are you today?"}
        ]
        await message.answer("💬 Let's talk in English!\n\n🤖 *Hi there! How are you today?*", parse_mode="Markdown", reply_markup=stop_kb)






@dp.message_handler(lambda msg: msg.text.lower() == "стоп диалог")
async def stop_conversation(message: types.Message):
    uid = message.from_user.id
    dialog_state.pop(uid, None)
    lang = user_language.get(uid, "en")
    kb = main_kb_en if lang == "en" else main_kb_ko
    await message.answer("🛑 Диалог завершён.", reply_markup=kb)





@dp.message_handler(lambda msg: msg.text in ["👤 Personal page", "👤 내 정보"])
async def handle_profile(message: types.Message):
    uid = message.from_user.id
    result = user_results.get(uid)

    if not result:
        await message.answer("ℹ️ Вы ещё не проходили тест.")
        return

    text = "👤 Ваш профиль:\n"

    if "level" in result:
        level = result["level"]
        score = result["score"]
        total = result["total"]
        text += f"\n📘 **Английский язык**:\n"
        text += f"🔹 Уровень: *{level}*\n"
        text += f"✅ Правильных ответов: *{score} из {total}*\n"

    if "korean_level" in result:
        klevel = result["korean_level"]
        kscore = result["korean_score"]
        ktotal = result["korean_total"]
        text += f"\n📗 **Корейский язык**:\n"
        text += f"🔹 Уровень: *{klevel}*\n"
        text += f"✅ Правильных ответов: *{kscore} из {ktotal}*\n"

    await message.answer(text, parse_mode="Markdown")








@dp.message_handler(lambda msg: msg.text in ["🌐 Translater", "🌐 번역기"])
async def handle_translate_intro(message: types.Message):
    uid = message.from_user.id
    lang = user_language.get(uid, "en")
    translation_mode[uid] = True


    if lang == "ko":
        await message.answer("✍️ 번역할 문장을 입력하거나 말해주세요:", reply_markup=stop_kb)
    else:
        await message.answer("✍️ Напиши фразу для перевода:", reply_markup=stop_kb)





user_data = {}

@dp.message_handler(lambda msg: msg.text == "📝 Test")
async def handle_test_start(message: types.Message):
    uid = message.from_user.id
    lang = user_language.get(uid, "en")

    if lang == "ko":
        questions = load_korean_grammar_questions()
        if not questions or len(questions) < 60:
            await message.answer("😔 Недостаточно вопросов по корейскому.")
            return
        user_data[uid] = {
            "lang": "ko",
            "questions": questions,
            "current": 0,
            "score": 0
        }
        await message.answer("📘 Начинаем корейский тест. Выбирай правильные ответы!", reply_markup=stop_kb)
        await send_next_question(message)
    else:
        questions = load_all_questions()
        if not questions or len(questions) != 60:
            await message.answer("😔 Вопросы не найдены или их меньше 60.")
            return
        user_data[uid] = {
            "lang": "en",
            "questions": questions,
            "current": 0,
            "score": 0
        }
        await message.answer("📘 Начинаем английский тест. Выбирай правильные ответы!", reply_markup=stop_kb)
        await send_next_question(message)


async def send_korean_question(message: types.Message):
    uid = message.from_user.id
    data = user_data[uid]
    index = data["current"]

    if index >= len(data["questions"]):
        score = data["score"]
        total = len(data["questions"])
        level = get_korean_level(score, total)


      
        user_results[uid] = {
            **user_results.get(uid, {}),
            "korean_level": level,
            "korean_score": score,
            "korean_total": total
        }
        save_user_results()


        await message.answer(f"✅ 테스트 완료!\n\n🎯 한국어 수준: {level}", reply_markup=main_kb_ko)
        del user_data[uid]
        save_user_results()

        return

    q = data["questions"][index]
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(q["option_a"], q["option_b"], q["option_c"])
    kb.add(KeyboardButton("⛔ 정지"))

    await message.answer(f"{index+1}/60\n❓ {q['question']}", reply_markup=kb)

def get_korean_level(score, total):
    percent = score / total
    if percent >= 85:
        return "고급 (Продвинутый)"
    elif percent >= 50:
        return "중급 (Средний)"
    else:
        return "초급 (Начальный)"

    







async def send_next_question(message: types.Message):
    uid = message.from_user.id
    data = user_data[uid]

    if data["current"] >= len(data["questions"]):
        score = data["score"]
        total = len(data["questions"])
        lang = data.get("lang", "en")

        if lang == "ko":
            level = get_korean_level(score, total)
            user_results[uid] = {
                **user_results.get(uid, {}),
                "korean_score": score,
                "korean_total": total,
                "korean_level": level
            }

            await message.answer(f"✅ 테스트 완료!\n\n🎯 한국어 수준: {level}", reply_markup=main_kb_ko)

        else:
            level = determine_level(score, total)
            user_results[uid] = {
                **user_results.get(uid, {}),
                "score": score,
                "total": total,
                "level": level
            }

            save_user_results()

            kb = main_kb_en if lang == "en" else main_kb_ko
            await message.answer(f"✅ Тест завершён!\n🎓 Ваш уровень английского: {level}", reply_markup=kb)


        del user_data[uid]
        save_user_results()

        return

    q = data["questions"][data["current"]]
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(q["option_a"], q["option_b"], q["option_c"])
    kb.add(KeyboardButton("⛔ Стоп"))

    await message.answer(f"{data['current']+1}/60\n❓ {q['question']}", reply_markup=kb)




@dp.message_handler(lambda msg: msg.from_user.id in user_data)
async def handle_test_answer(message: types.Message):
    uid = message.from_user.id
    data = user_data[uid]
    q = data["questions"][data["current"]]
    text = message.text.strip()

  
    if text not in [q["option_a"], q["option_b"], q["option_c"]]:
        return

  
    is_correct = text == q["correct"]
    if is_correct:
        data["score"] += 1
        await message.answer("✅ Верно!")
    else:
        await message.answer(f"❌ Неверно, правильный ответ: *{q['correct']}*", parse_mode="Markdown")

 
    data["current"] += 1

    if data.get("lang") == "ko":
        await send_korean_question(message)
    else:
        await send_next_question(message)



def load_korean_grammar_questions():
    questions = []
    with open("korean_grammar_questions.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            questions.append(row)
    return questions


@dp.message_handler(lambda msg: msg.text in ["📝 문법 테스트", "🇰🇷 문법 테스트"])

async def start_korean_grammar_test(message: types.Message):
    translation_mode[message.from_user.id] = False

    uid = message.from_user.id
    questions = load_korean_grammar_questions()

    if not questions or len(questions) < 60:
        await message.answer("😔 테스트 문제가 충분하지 않습니다.")
        return

    user_data[uid] = {
        "lang": "ko",
        "questions": questions,
        "current": 0,
        "score": 0
    }

    await message.answer("📘 한국어 문법 테스트를 시작합니다. 총 60문제입니다.", reply_markup=stop_kb)
    await send_korean_question(message)



def determine_level(score, total):
    percent = score / total
    if percent < 0.2:
        return "A1"
    elif percent < 0.35:
        return "A2"
    elif percent < 0.5:
        return "B1"
    elif percent < 0.7:
        return "B2"
    elif percent < 0.9:
        return "C1"
    else:
        return "C2"







@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice_message(message: types.Message):
    uid = message.from_user.id
    lang = user_language.get(uid, "en")
    mode = active_mode.get(uid)

    file_info = await bot.get_file(message.voice.file_id)
    await bot.download_file(file_info.file_path, "voice.ogg")
    os.system("ffmpeg -y -i voice.ogg -ar 16000 -ac 1 voice.wav")

    recognized_text = transcribe("voice.wav", lang=lang)
    print(f"🎤 Режим: {mode} | Распознано: {recognized_text}")

    if mode == "conversation" and uid in dialog_state:
        dialog_state[uid].append({"role": "user", "content": recognized_text})

        prompt = "\n".join([
            f"{'User' if entry['role'] == 'user' else 'AI'}: {entry['content']}"
            for entry in dialog_state[uid][-6:]
        ]) + "\nAI:"

        try:
            response_raw = ask_mistral(prompt)
            ai_response = response_raw.strip().split("\n")[0].removeprefix("AI:").strip()

            dialog_state[uid].append({"role": "assistant", "content": ai_response})

            await message.answer(f"🤖 {ai_response}")
            audio_path = f"response_{uid}.wav"
            synthesize_speech(ai_response, audio_path, lang=lang)
            with open(audio_path, "rb") as voice_file:
                await bot.send_voice(chat_id=message.chat.id, voice=voice_file)
            os.remove(audio_path)

        except Exception as e:
            await message.answer(f"⚠️ Ошибка при генерации ответа: {e}")

    
    elif mode == "speaking" and uid in speak_sessions:
        # Сравнение с заданной фразой
        expected = speak_sessions[uid]["phrases"][speak_sessions[uid]["current"]]
        if normalize(recognized_text) == normalize(expected):
            await message.answer("✅ Всё верно!" if lang == "en" else "✅ 아주 잘했어요!")
        else:
            await message.answer(
                f"❌ Было сказано: *{recognized_text}*\n✅ Правильно: *{expected}*",
                parse_mode="Markdown"
            )
        speak_sessions[uid]["current"] += 1
        await send_speak_phrase(message, uid)
    
    else:
        await message.answer("⚠️ Не выбран режим. Нажмите кнопку в главном меню.")



@dp.message_handler(
    lambda msg: (
        
        translation_mode.get((msg.from_user.id), False)
    ),
    content_types=types.ContentType.TEXT
)



async def handle_translation(message: types.Message):
    user_text = message.text.strip()
    await message.answer("🤖 Перевожу через Mistral...")
    uid = message.from_user.id
    lang = user_language.get(uid, "en")


    if lang == "ko":
        prompt = f"""
Ты профессиональный переводчик, свободно владеющий корейским и русским языками.

Твоя задача:
🔹 Определи язык фразы — русский или корейский.
🔹 Если фраза на **корейском**, переведи её на **русский**.
🔹 Если фраза на **русском**, переведи её на **корейский**.
🔹 Перевод должен быть точным по смыслу. Если фраза — идиома, сленг или фразеологизм, переводи по значению, а не дословно.

Дополнительно:
— После перевода, кратко объясни смысл выражения.
— Приведи возможные синонимы на **корейском**.
— Приведи 1–2 примера предложений на исходном языке с переводом.

Фраза:
\"\"\"{user_text}\"\"\""""

    else:
        prompt = f"""
Ты профессиональный переводчик, свободно владеющий английским и русским языками.

Твоя задача:
🔹 Определи язык фразы — русский или английский.
🔹 Если фраза на **английском**, переведи её на **русский**.
🔹 Если фраза на **русском**, переведи её на **английский**.
🔹 Перевод должен быть точным по смыслу. Если фраза — идиома, сленг или фразеологизм, переводи по значению, а не дословно.

Дополнительно:
— После перевода, кратко объясни смысл выражения.
— Приведи возможные синонимы на **английском**.
— Приведи 1–2 примера предложений на исходном языке с переводом.

Фраза:
\"\"\"{user_text}\"\"\""""

    try:
        response = ask_mistral(prompt)
        await message.answer(response)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка при запросе к ИИ: {e}")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
