import asyncio
import logging
import subprocess
from aiogram import Bot, Dispatcher
from aiogram.enums import ContentType
from aiogram.filters import Command
from aiogram.types import Message
import config
import pandas as pd


admin = int(config.info.admin.get_secret_value())
dp = Dispatcher()
bot = Bot(token=config.info.telegram_bot_api.get_secret_value())
logging.basicConfig(level=logging.INFO)


process = None


@dp.message(Command('start'))
async def work(message: Message):
    if message.from_user.id == admin:
        await message.answer('/start_bot - Запускает бота \n'
                             '/stop_bot - Выключает бота \n'
                             '/info - Показывает текущие настройки бота \n'
                             '/sol_usdt - Переключается между SOL и USDT \n'
                             '/raydium_jupiter - Переключается между Raydium и Jupiter \n'
                             'token <адрес токена> - Меняет адрес токена \n'
                             'sleep_min <число> - Время минимального перерыва между транзакциями в секундах \n'
                             'sleep_max <число> - Время максимального перерыва между транзакциями в секундах \n'
                             'volume <число> - Объем в USDT \n'
                             'Отправка txt файла добавляет приватники кошельков на которых будет крутиться объем\n'
                             )
    else:
        await message.answer('Вы не являетесь администратором.')


@dp.message(Command('start_bot'))
async def start_futures_bot(message: Message):
    if message.from_user.id == admin:
        global process
        if process is None:
            command = [
                'python',
                'models.py',
            ]
            process = subprocess.Popen(command)
            await message.answer('Запустил бота')
        else:
            await message.answer('Бот уже запущен')
    else:
        await message.answer('Вы не являетесь администратором.')


@dp.message(Command('stop_bot'))
async def stop(message: Message):
    if message.from_user.id == admin:
        global process
        if process is not None:
            process.terminate()
            process = None
            await message.answer('Выключил бота')
        else:
            await message.answer('Бот уже выключен')
    else:
        await message.answer('Вы не являетесь администратором.')


@dp.message(Command('sol_usdt'))
async def stop(message: Message):
    if message.from_user.id == admin:
        df = pd.read_csv('settings.csv')
        if df['usdt'][0]:
            df['usdt'][0] = False
            df.to_csv('settings.csv', index=False)
            await message.answer('Включил прокрут через SOL')
        else:
            df['usdt'][0] = True
            df.to_csv('settings.csv', index=False)
            await message.answer('Включил прокрут через USDT')
    else:
        await message.answer('Вы не являетесь администратором.')


@dp.message(Command('raydium_jupiter'))
async def stop(message: Message):
    if message.from_user.id == admin:
        df = pd.read_csv('settings.csv')
        if df['raydium'][0]:
            df['raydium'][0] = False
            df.to_csv('settings.csv', index=False)
            await message.answer('Включил прокрут через Jupyter')
        else:
            df['raydium'][0] = True
            df.to_csv('settings.csv', index=False)
            await message.answer('Включил прокрут через Raydium')
    else:
        await message.answer('Вы не являетесь администратором.')


@dp.message(Command('info'))
async def stop(message: Message):
    if message.from_user.id == admin:
        dct = pd.read_csv('settings.csv').to_dict('records')[0]
        value = 'USDT' if dct['usdt'] else 'SOL'
        dex = 'Raydium' if dct['raydium'] else 'Jupyter'

        await message.answer(f'Value usdt: {dct["value"]}\n'
                             f'Объем крутится через {dex} в {value}\n'
                             f'Минимальный перерыв между транзами: {dct["sleep_min"]}\n'
                             f'Максимальный перерыв между транзами: {dct["sleep_max"]}\n')
    else:
        await message.answer('Вы не являетесь администратором.')


@dp.message()
async def stop(message: Message):
    if message.from_user.id == admin:
        if message.content_type == ContentType.DOCUMENT:
            file_id = message.document.file_id
            file_info = await bot.get_file(file_id)
            file_path = file_info.file_path
            await bot.download_file(file_path, 'private_keys.txt')
            await message.reply(f'Вы добавили новые приватники')

        if 'sleep_max' in message.text:
            sleep_max = message.text.split()[1]
            df = pd.read_csv('settings.csv')
            df['sleep_max'][0] = int(sleep_max)
            df.to_csv('settings.csv', index=False)
            await message.reply(f'Вы имзменили максимальный перерыв между транзами на {sleep_max}')

        if 'token' in message.text:
            token = message.text.split()[1]
            df = pd.read_csv('settings.csv')
            df['token'][0] = str(token)
            df.to_csv('settings.csv', index=False)
            await message.reply(f'Вы имзменили адрес токена на {token}')

        if 'sleep_min' in message.text:
            sleep_min = message.text.split()[1]
            df = pd.read_csv('settings.csv')
            df['sleep_min'][0] = int(sleep_min)
            df.to_csv('settings.csv', index=False)
            await message.reply(f'Вы имзменили минимальный перерыв между транзами на {sleep_min}')

        if 'volume' in message.text.lower():
            volume = message.text.split()[1]
            df = pd.read_csv('settings.csv')
            df['value'][0] = int(volume)
            df.to_csv('settings.csv', index=False)
            await message.reply(f'Вы имзменили объем прокрутки на {volume} USDT')

    else:
        await message.answer('Вы не являетесь администратором.')


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
