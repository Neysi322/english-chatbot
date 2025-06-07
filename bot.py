import logging
import os
import pyttsx3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputFile
from aiogram.utils import executor
from mistral_client import ask_mistral
from whisper_transcriber import transcribe
from test_engine import load_all_questions, evaluate_answer
from TTS.api import TTS

tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False, gpu=False)



API_TOKEN = '7958579468:AAF3d-BnWMxwt8ct0LNlWdBQaR16-Wy0JvM'  # ЗАМЕНИ на свой токен

# user_results сохраняет результаты по user_id
user_results = {}

dialog_state = {}  # {user_id: [history]}


logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(lambda msg: msg.from_user.id in dialog_state)
async def continue_conversation(message: types.Message):
    uid = message.from_user.id
    user_input = message.text.strip()

    # Прерывание диалога при нажатии на другие кнопки
    if user_input in ["📊 Пройти тест", "🔤 Переводчик", "👤 Личный кабинет", "💬 Диалог с ИИ"]:
        dialog_state.pop(uid, None)
        await message.answer("🛑 Вы прервали диалог с ИИ.", reply_markup=main_kb)
        return

    dialog_state[uid].append({"role": "user", "content": user_input})

    # Подготовка prompt в виде диалога
    prompt = "\n".join([
        f"{'User' if entry['role'] == 'user' else 'AI'}: {entry['content']}"
        for entry in dialog_state[uid][-6:]
    ])
    prompt += "\nAI:"

    try:
        response_raw = ask_mistral(prompt)
        ai_response = response_raw.strip().split("\n")[0].removeprefix("AI:").strip()

        # Добавляем ответ ИИ в историю
        dialog_state[uid].append({"role": "assistant", "content": ai_response})

        # Отправка текстом
        await message.answer(f"🤖 {ai_response}")

        # Генерация речи
        audio_path = f"response_{uid}.wav"
        tts.tts_to_file(text=ai_response, file_path=audio_path)
        with open(audio_path, "rb") as voice_file:
            await bot.send_voice(chat_id=message.chat.id, voice=voice_file)
        os.remove(audio_path)

    except Exception as e:
        await message.answer(f"⚠️ Ошибка генерации или синтеза: {e}")



# Главное меню
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add(KeyboardButton("🔤 Переводчик"), KeyboardButton("📊 Пройти тест"), KeyboardButton("👤 Личный кабинет"), KeyboardButton("💬 Диалог с ИИ"))


def synthesize_offline(text, filename):
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)  # скорость речи
    engine.setProperty('voice', 'english')  # можно уточнить голос, если установлен
    engine.save_to_file(text, filename)
    engine.runAndWait()

def synthesize_speech(text, filename):
    tts.tts_to_file(text=text, file_path=filename)

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для изучения английского языка.\n"
        "Выбери опцию ниже и начни!",
        reply_markup=main_kb
    )

@dp.message_handler(lambda msg: msg.text == "💬 Диалог с ИИ")
async def start_conversation(message: types.Message):
    uid = message.from_user.id
    dialog_state[uid] = [
        {"role": "system", "content": "You are a friendly English-speaking partner for conversation practice. Keep the dialog simple and natural."},
        {"role": "assistant", "content": "Hi there! How are you today?"}
    ]
    await message.answer("💬 Let's talk in English!\n\n🤖 *Hi there! How are you today?*", parse_mode="Markdown")



@dp.message_handler(lambda msg: msg.text.lower() == "стоп диалог")
async def stop_conversation(message: types.Message):
    uid = message.from_user.id
    dialog_state.pop(uid, None)
    await message.answer("🛑 Диалог завершён.", reply_markup=main_kb)




@dp.message_handler(lambda msg: msg.text == "👤 Личный кабинет")
async def handle_profile(message: types.Message):
    uid = message.from_user.id
    result = user_results.get(uid)

    if not result:
        await message.answer("ℹ️ Вы ещё не проходили тест. Нажмите «📊 Пройти тест», чтобы начать.")
        return

    await message.answer(
        f"👤 Ваш профиль:\n\n"
        f"🎯 Уровень английского: {result['level']}\n"
        f"✅ Правильных ответов: {result['score']} из {result['total']}"
    )


# === Переводчик ===

@dp.message_handler(lambda msg: msg.text == "🔤 Переводчик")
async def handle_translate_intro(message: types.Message):
    await message.answer("✍️ Напиши или продиктуй фразу для перевода:")

# === Грамматический тест ===

user_data = {}

@dp.message_handler(lambda msg: "Пройти тест" in msg.text)
async def handle_test_start(message: types.Message):
    print("Кнопка 'Пройти тест' нажата")  # отладка
    questions = load_all_questions()

    if not questions or len(questions) != 60:
        await message.answer("😔 Вопросы не найдены или их меньше 60.")
        return

    user_data[message.from_user.id] = {
        "questions": questions,
        "current": 0,
        "score": 0
    }

    await message.answer("📘 Начинаем грамматический тест из 60 вопросов. Выбирай правильные ответы!")
    await send_next_question(message)

async def send_next_question(message: types.Message):
    uid = message.from_user.id
    data = user_data[uid]

    if data["current"] >= len(data["questions"]):
        score = data["score"]
        total = len(data["questions"])
        level = determine_level(score, total)

        # Сохраняем результат в личный кабинет
        user_results[uid] = {
            "score": score,
            "total": total,
            "level": level
        }

        await message.answer(f"✅ Тест завершён!\n"
                            
                            f"🎓 Ваш уровень английского: {level}")
        del user_data[uid]
        return


    q = data["questions"][data["current"]]
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(q["option_a"], q["option_b"], q["option_c"])
    await message.answer(f"❓ {q['question']}", reply_markup=kb)

@dp.message_handler(lambda msg: msg.from_user.id in user_data)
async def handle_test_answer(message: types.Message):
    uid = message.from_user.id
    data = user_data[uid]
    q = data["questions"][data["current"]]
    correct = evaluate_answer(message.text, q["correct"])

    if correct:
        data["score"] += 1
        await message.answer("✅ Верно!")
    else:
        await message.answer(f"❌ Неверно. Правильный ответ: {q['correct']}")

    data["current"] += 1
    await send_next_question(message)

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

# === Обработка голосового перевода ===

@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice(message: types.Message):
    uid = message.from_user.id

    try:
        # Скачиваем и конвертируем голосовое сообщение
        file_info = await bot.get_file(message.voice.file_id)
        input_path = "voice.ogg"
        output_path = "voice.wav"
        await bot.download_file(file_info.file_path, input_path)
        os.system(f"ffmpeg -y -i {input_path} -ar 16000 -ac 1 {output_path}")

        recognized_text = transcribe(output_path).strip()

        if not recognized_text:
            await message.answer("😕 Не удалось распознать речь. Попробуй снова.")
            return

        # === 📌 Если пользователь находится в режиме Диалога с ИИ ===
        if uid in dialog_state:
            dialog_state[uid].append({"role": "user", "content": recognized_text})

            prompt = "\n".join([
                f"{'User' if x['role'] == 'user' else 'AI'}: {x['content']}"
                for x in dialog_state[uid][-6:]
            ]) + "\nAI:"

            ai_response = ask_mistral(prompt).strip().split("\n")[0].removeprefix("AI:").strip()
            dialog_state[uid].append({"role": "assistant", "content": ai_response})

            await message.answer(f"🤖 {ai_response}")

            audio_path = f"response_{uid}.wav"
            tts.tts_to_file(text=ai_response, file_path=audio_path)
            with open(audio_path, "rb") as voice_file:
                await bot.send_voice(chat_id=message.chat.id, voice=voice_file)
            os.remove(audio_path)

        else:
            # === 🧠 Обычный режим — переводчик ===
            await message.answer(f"📝 Распознанный текст:\n{recognized_text}")
            await message.answer("🤖 Перевожу...")

            prompt = f"""
Ты профессиональный лингвист и носитель английского языка.
Твоя задача — перевести следующее выражение на английский или русский язык (в зависимости от языка исходной фразы).
Важно:
- Используй естественные формулировки.
- Если выражение — идиома или фразеологизм, подбери аналог.
- Добавь все возможные переводы.
- Приведи синонимы на целевом языке.
- Примеры в предложении.
- Объяснение на русском языке.

Фраза:
\"\"\"{recognized_text}\"\"\""""

            response = ask_mistral(prompt)
            await message.answer(response)

    except Exception as e:
        await message.answer(f"⚠️ Ошибка при обработке аудио: {e}")


# === Обработка текстового ввода ===

@dp.message_handler(lambda msg: msg.text not in ["📊 Пройти тест", "🔤 Переводчик"], content_types=types.ContentType.TEXT)
async def handle_translation(message: types.Message):
    user_text = message.text.strip()
    await message.answer("🤖 Перевожу через Mistral...")

    prompt = f"""
Ты профессиональный лингвист и носитель английского языка.
Твоя задача — перевести следующее выражение на английский или русский язык (в зависимости от языка исходной фразы).
Важно:
- Используй естественные формулировки.
- Если выражение — идиома или фразеологизм, подбери аналог.
- Добавь все возможные переводы.
- Приведи синонимы на целевом языке.
- Примеры в предложении.
- Объяснение на русском языке.

Фраза:
\"\"\"{user_text}\"\"\"
"""
    try:
        response = ask_mistral(prompt)
        await message.answer(response)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка при запросе к ИИ: {e}")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)