import serial
import time
import csv
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

NSEC = 0.2
INTERVAL_SECONDS = 300  # how often to read from the weather station (seconds)

LOG_DIR = "/opt/CLF_code/logs"
CSV_FILE = os.path.join(LOG_DIR, "weather_log.csv")
LOG_FILE = os.path.join(LOG_DIR, "weather.log")


def configure_logging():
    """Configure the 'weather' logger with daily rotation."""
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("weather")
    logger.setLevel(logging.INFO)

    # Avoid adding multiple handlers if configure_logging() is called more than once
    if not logger.handlers:
        # File handler with daily rotation at midnight
        file_handler = TimedRotatingFileHandler(
            LOG_FILE,
            when="midnight",
            backupCount=14,      # keep last 14 days of logs
            encoding="utf-8"
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        )
        file_handler.setFormatter(formatter)

        # Optional: also log to console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


def read_weather():
    """Read a single set of data from the weather station and return it as a dict."""
    s = serial.Serial("/dev/ttyr07", 9600)

    # init sequence
    s.write("\r\n".encode())
    time.sleep(NSEC)
    s.write("\r\n".encode())
    time.sleep(NSEC)
    s.read_all()
    s.write("G\r\n".encode())
    time.sleep(NSEC)
    s.read_all()

    # request data
    s.write("1B\r\n".encode())
    time.sleep(NSEC)
    s.read_all()

    s.write("1D\r\n".encode())
    time.sleep(NSEC)
    s.read_until('\n'.encode())
    out = s.read_until('\n'.encode())[:-2].decode()
    out = out + " " + s.read_until('\n'.encode())[1:-2].decode()

    # parse
    data = []
    for m in out.split():
        data.append(float(m.split('+')[1]))

    s.close()

    # build dict
    d = {}
    d["code"] = data[0]
    d["year"] = data[1]
    d["day"] = data[2]
    d["hour"] = int(data[3] / 100)
    d["minute"] = int(data[3] - int(data[3] / 100) * 100)
    d["temperature"] = data[4]
    d["humidity"] = data[5]
    d["curwspeed"] = data[6]
    d["avgwspeed"] = data[7]
    d["maxwspeed"] = data[8]
    d["pressure"] = data[-1]

    return d, out  # return both parsed dict and raw string


def prepare_csv():
    """Create the CSV file with header if it does not exist."""
    os.makedirs(LOG_DIR, exist_ok=True)

    if not os.path.isfile(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "timestamp",
                "code", "year", "day", "hour", "minute",
                "temperature", "humidity",
                "curwspeed", "avgwspeed", "maxwspeed",
                "pressure"
            ])


def save_csv(data_dict):
    """Append one row to the CSV file."""
    with open(CSV_FILE, "a", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            datetime.now().isoformat(timespec="seconds"),
            data_dict["code"], data_dict["year"], data_dict["day"],
            data_dict["hour"], data_dict["minute"],
            data_dict["temperature"], data_dict["humidity"],
            data_dict["curwspeed"], data_dict["avgwspeed"], data_dict["maxwspeed"],
            data_dict["pressure"]
        ])


def main():
    logger = configure_logging()
    prepare_csv()

    logger.info("Weather logging started. Reading every %d seconds.", INTERVAL_SECONDS)

    while True:
        try:
            data_dict, raw_string = read_weather()

            # Log raw line and parsed data
            logger.debug("Raw weather string: %s", raw_string)
            logger.info(
                "Weather data: T=%.2f°C RH=%.2f%% P=%.1f hPa curW=%.2f avgW=%.2f maxW=%.2f",
                data_dict["temperature"],
                data_dict["humidity"],
                data_dict["pressure"],
                data_dict["curwspeed"],
                data_dict["avgwspeed"],
                data_dict["maxwspeed"],
            )

            # Print to console (optional)
            #print("\n--- WEATHER READING ---")
            #for k, v in data_dict.items():
            #    print(f"{k}: {v}")

            # Save to CSV
            save_csv(data_dict)

        except Exception as e:
            logger.exception("Error while reading or logging weather data: %s", e)

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

