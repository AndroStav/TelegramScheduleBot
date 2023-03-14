import asyncio
from collections import deque
import configparser
import csv
from datetime import datetime
from typing import NamedTuple, Optional, Tuple
import logging

import telegram


TIME_TABLE = deque()
LESSONS_LIST = deque()
GREETINGS_LIST = deque()

SUBJECTS_DICT = {}


class SubjectData (NamedTuple):
    image_path: str
    link: deque


class Status:
    def __init__(self, is_success: bool, text: str):
        self.is_success = is_success
        self.text = text

    def log(self) -> bool:
        if self.is_success:
            logging.info(f"{get_current_time_text()} {self.text}")
        else:
            logging.error(f"{get_current_time_text()} {self.text}")
        return self.is_success


def get_current_period(number_of_periods: int, period_duration: int, start_of_first_period: datetime) -> int:
    today = datetime.today()

    days_since_start_date = (today - start_of_first_period).days
    current_period_number = (days_since_start_date / period_duration) + 1
    for n in range(number_of_periods, 0, -1):
        if current_period_number % n == 0 or n == 1:
            return n


def get_current_time_text() -> str:
    return datetime.now().strftime("%F %T.%f")[:-3]


def get_next_lesson_index() -> int:
    for i, lesson in enumerate(TIME_TABLE):
        if datetime.now() <= lesson[0] and LESSONS_LIST[i] != '':
            return i
    else:
        return -1


def load_config(filename: str) -> Tuple[Optional[dict], Status]:
    config = configparser.ConfigParser()
    try:
        config.read(filename)
    except configparser.Error as e:
        return None, Status(False, f"Error reading configuration file: {e}")

    result = {}
    for section in config.sections():
        for key, value in config.items(section):
            result[key] = value

    return result, Status(True, "Config read successfully")


def load_data(subjects_path: str, period_path: str, time_table_path: str) -> Status:
    SUBJECTS_DICT.clear()
    LESSONS_LIST.clear()
    TIME_TABLE.clear()
    try:
        with open(subjects_path, mode='r', encoding="utf-8") as subjects_file:
            subjects_csv_reader = csv.reader(subjects_file)
            for row in subjects_csv_reader:
                temp = deque()
                for i in range(2, len(row)):
                    temp.append(row[i])
                subject = SubjectData(row[1], temp)
                SUBJECTS_DICT[(row[0]).lower()] = subject

        with open(period_path, mode='r', encoding="utf-8") as schedule_file:
            schedule_csv_reader = csv.reader(schedule_file)
            for row, column in enumerate(schedule_csv_reader):
                if row == datetime.now().weekday():
                    LESSONS_LIST.extend(column)

        with open(time_table_path, mode='r', encoding="utf-8") as time_table_file:
            time_table_reader = csv.reader(time_table_file)
            for row in time_table_reader:
                row_list = deque()
                for column in row:
                    time_t = datetime.strptime(column, "%H:%M:%S")
                    row_list.append(datetime.now().replace(hour=time_t.hour, minute=time_t.minute, second=time_t.second))
                TIME_TABLE.append(row_list)
        return Status(True, f"Files were successfully loaded")

    except csv.Error as e:
        return Status(False, f"Error reading CSV file: {e}")

    except FileNotFoundError as e:
        return Status(False, f"File not found: {e}")

    except Exception as e:
        return Status(False, f"An unknown error has occurred: {e}")


async def delete_message(bot: telegram.Bot, message_id: int, channel_id: str) -> Status:
    try:
        await bot.delete_message(channel_id, message_id)
        return Status(True, f"Message({message_id}) was successfully deleted")

    except telegram.error.TelegramError as e:
        return Status(False, f"An error occurred during deleting of message: {e}")


async def send_message(bot: telegram.Bot, subject_name: str, channel_id: str) -> \
        Tuple[Optional[telegram.Message], Status]:
    photo_path = None
    try:
        subject: Optional[SubjectData] = SUBJECTS_DICT.get(subject_name.lower())
        if subject is None:
            raise ValueError(f"Subject {subject_name} not found in SUBJECTS_DICT")
        str_link = ''
        for i in range(len(subject.link)):
            str_link += f"\n{subject.link[i]}"
        message = f"{subject_name}\n{str_link}"
        photo_path = subject.image_path
        with open(photo_path, 'rb') as photo:
            message = await bot.send_photo(channel_id, photo=photo, caption=message)
        return message, Status(True, f"Message ({message.message_id}) was successfully sent")

    except FileNotFoundError:
        return None, Status(False, f"Photo file not found: {photo_path}")

    except OSError as e:
        return None, Status(False, f"Error opening photo file: {e}")

    except ValueError as e:
        return None, Status(False, str(e))

    except telegram.error.TelegramError as e:
        return None, Status(False, f"Error sending message: {e}")

    except Exception as e:
        return None, Status(False, f"An unknown error has occurred: {e}")


async def main() -> None:
    config, status = load_config("config.ini")
    logging.basicConfig(filename="bot.log", encoding="utf-8", level=logging.DEBUG)

    if not status.log():
        raise Exception(status.text)

    token = config["bot_token"]
    channel_id = config["channel_id"]
    bot = telegram.Bot(token)

    current_period = get_current_period(int(config["number_of_periods"]),
                                        int(config["period_duration"]),
                                        datetime.strptime(config["start_of_first_period"], "%Y/%M/%d"))
    status = load_data(config["subjects_dict_file_path"],
                       config["standard_period_file_path"].replace("$", str(current_period)),
                       config["time_table_file_path"])

    if not status.log():
        raise Exception(status.text)

    while True:
        next_lesson_index = get_next_lesson_index()

        if next_lesson_index < 0:
            now = datetime.now()
            wait_time = datetime(now.year, now.month, now.day, 8, 00) - now

            await asyncio.sleep(wait_time.seconds)

            current_period = get_current_period(int(config["number_of_periods"]),
                                                int(config["period_duration"]),
                                                datetime.strptime(config["start_of_first_period"], "%Y/%M/%d"))
            load_data(config["subjects_dict_file_path"],
                      config["standard_period_file_path"].replace("$", str(current_period)),
                      config["time_table_file_path"])

        else:
            subject = LESSONS_LIST[next_lesson_index]
            start_time, end_time = TIME_TABLE[next_lesson_index]

            await asyncio.sleep((start_time - datetime.now()).seconds)
            msg, status = await send_message(bot, subject, channel_id)

            if not status.log():
                raise Exception(status.text)

            await asyncio.sleep((end_time - datetime.now()).seconds)
            status = await delete_message(bot, msg.message_id, channel_id)

            if not status.log():
                raise Exception(status.text)


if __name__ == "__main__":
    asyncio.run(main())
