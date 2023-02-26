from collections import deque
import configparser
import csv
from datetime import datetime
from typing import NamedTuple, Optional, Tuple
import logging

import pause
import telebot

TIME_TABLE = deque()
LESSONS_LIST = deque()
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
                if row == datetime.today().weekday():
                    LESSONS_LIST.extend(column)

        with open(time_table_path, mode='r', encoding="utf-8") as time_table_file:
            time_table_reader = csv.reader(time_table_file)
            for row in time_table_reader:
                row_list = deque()
                for column in row:
                    time = datetime.strptime(column, "%H:%M:%S")
                    row_list.append(datetime.now().replace(hour=time.hour, minute=time.minute, second=time.second))
                TIME_TABLE.append(row_list)
        return Status(True, f"Files were successfully loaded")

    except csv.Error as e:
        return Status(False, f"Error reading CSV file: {e}")

    except FileNotFoundError as e:
        return Status(False, f"File not found: {e}")

    except Exception as e:
        return Status(False, f"An unknown error has occurred: {e}")


def delete_message(bot: telebot.TeleBot, message_id: int, channel_id: str) -> Status:
    try:
        bot.delete_message(channel_id, message_id)
        return Status(True, f"Message({message_id}) was successfully deleted")

    except telebot.apihelper.ApiException as e:
        return Status(False, f"Error deleting message: {message_id}. {e}")


def send_message(bot: telebot.TeleBot, subject_name: str, channel_id: str) -> \
        Tuple[Optional[telebot.types.Message], Status]:
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
            sent_message = bot.send_photo(channel_id, photo=photo, caption=message)

        return sent_message, Status(True, f"Message ({sent_message.message_id}) was successfully sent")

    except FileNotFoundError:
        return None, Status(False, f"Photo file not found: {photo_path}")

    except OSError as e:
        return None, Status(False, f"Error opening photo file: {e}")

    except ValueError as e:
        return None, Status(False, str(e))

    except telebot.apihelper.ApiException as e:
        return None, Status(False, f"Error sending message: {e}")

    except Exception as e:
        return None, Status(False, f"An unknown error has occurred: {e}")


def main() -> None:
    config, status = load_config("config.ini")
    logging.basicConfig(filename="bot.log", encoding="utf-8", level=logging.DEBUG)

    if not status.log():
        raise Exception(status.text)

    token = config["bot_token"]
    channel_id = config["channel_id"]
    bot = telebot.TeleBot(token)

    current_period = get_current_period(int(config["number_of_periods"]),
                                        int(config["period_duration"]),
                                        datetime.strptime(config["start_of_first_period"], "%Y/%M/%d"))
    status = load_data(config["subjects_dict_file_path"],
                       config["standard_period_file_path"].replace("$", str(current_period)),
                       config["time_table_file_path"])

    if not status.log():
        raise Exception(status.text)

    for i in range(len(LESSONS_LIST)):
        next_lesson_index = get_next_lesson_index()

        if next_lesson_index < 0:
            return

        subject = LESSONS_LIST[next_lesson_index]
        start_time, end_time = TIME_TABLE[next_lesson_index]

        pause.until(start_time)
        msg, status = send_message(bot, subject, channel_id)

        if not status.log():
            raise Exception(status.text)

        pause.until(end_time)
        status = delete_message(bot, msg.message_id, channel_id)

        if not status.log():
            raise Exception(status.text)


if __name__ == "__main__":
    main()

#    MIT License

#Copyright (c) 2023 Dmytro Pukhalskyi

#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:

#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.

#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.
