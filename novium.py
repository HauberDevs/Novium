import tkinter as tk
import requests
import json
import os
import sys
from datetime import datetime, timedelta
import ctypes
import logging
import threading
from PIL import Image, ImageTk

APP_VERSION = "1.1"
CONFIG_FILE = "config.json"
LOGS_FOLDER_NAME = "logs"
IMAGE_FOLDER = "images"
STOP_SIGN_IMAGE = "stopsign.png"

passenger_frontend_error_fallback_text = (
   "Aufgrund einer technischen Störung ist diese Fahrtzielanzeige\n"
   "vorübergehend außer Betrieb. Bitte beachten sie den\n"
   "Fahrplanaushang oder die Anzeigen am Gleis."
   "\n\n"
   "Wir entschuldigen uns für die Unannehmlichkeiten\n"
   "und wünschen ihnen eine schöne Reise."
)

no_departures_fallback_text = (
    "Derzeit keine Abfahrten von dieser Haltestelle.\n"
    "Bitte Fahrplanaushang beachten."
)

running = True
is_closing = False

clock_after_id = None
fetch_after_id = None

def get_build_timestamp():
    try:
        if getattr(sys, 'frozen', False):
            # Frozen executable (e.g., cx_Freeze or py2exe)
            path = sys.executable
        else:
            # Running as a script
            path = os.path.abspath(__file__)

        timestamp = os.path.getmtime(path)
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%A, %B %d, %Y %H:%M:%S")
    except Exception:
        return "Unknown"

def setup_logging():
    try:
        log_dir = os.path.join(os.getcwd(), LOGS_FOLDER_NAME)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = os.path.join(log_dir, timestamp + ".log")

        logging.basicConfig(
            filename=log_file,
            level=logging.DEBUG,
            format='[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        logging.info("Starting Novium Version {0}, compiled {1}".format(APP_VERSION, get_build_timestamp()))
    except Exception:
        pass

def load_font(ttf_path):
    """Load a .ttf font from a file without installing it system-wide."""
    if os.path.exists(ttf_path):
        FR_PRIVATE = 0x10
        try:
            ctypes.windll.gdi32.AddFontResourceExW(ttf_path, FR_PRIVATE, 0)
            logging.info("Loaded font: {0}".format(ttf_path))
        except Exception as e:
            logging.error("Failed to load font: {0}, Error: {1}".format(ttf_path, e))
    else:
        logging.error("Font not found: {0}".format(ttf_path))

def safe_after_cancel(root, after_id):
    try:
        if after_id is not None:
            root.after_cancel(after_id)
    except Exception:
        pass


def update_clock(hour_label, colon_label, minute_label, toggle_colon_visibility, header_bg_color):
    global clock_after_id, running, is_closing
    if not running or is_closing:
        return
    try:
        current_time = datetime.now()
        hour = current_time.strftime("%H")
        minute = current_time.strftime("%M")

        if hour_label.winfo_exists():
            hour_label.config(text=hour)
        if minute_label.winfo_exists():
            minute_label.config(text=minute)

        if toggle_colon_visibility[0]:
            if colon_label.winfo_exists():
                colon_label.config(fg="white")
        else:
            if colon_label.winfo_exists():
                colon_label.config(fg=header_bg_color)

        toggle_colon_visibility[0] = not toggle_colon_visibility[0]

        clock_after_id = hour_label.after(1000, lambda: update_clock(hour_label, colon_label, minute_label, toggle_colon_visibility, header_bg_color))
    except Exception:
        logging.exception("Error updating clock")
        
def clear_content(content_frame):
    try:
        if content_frame.winfo_exists():
            for widget in content_frame.winfo_children():
                widget.destroy()
    except Exception:
        logging.exception("Error clearing content frame")


def format_departure_time(departure_datetime_str):
    try:
        if not isinstance(departure_datetime_str, str):
            return "N/A"
        departure_time = datetime.strptime(departure_datetime_str[:19], "%Y-%m-%dT%H:%M:%S")
        now = datetime.now()
        time_difference = (departure_time - now).total_seconds()
        if 0 < time_difference <= 44 * 60:
            minutes = int(time_difference // 60)
            return "{0} min".format(minutes)
        elif time_difference <= 0:
            return "Jetzt "
        else:
            return departure_time.strftime("%H:%M")
    except Exception:
        logging.exception("Failed to format departure time")
        return "N/A"

def start_marquee(label, text, delay=150):
    """Make label text scroll horizontally if it's too wide."""
    # Store the full text and current position in label object
    label.full_text = text + "   "  # Add spaces for smooth scrolling
    label.pos = 0

    def scroll():
        if not label.winfo_exists():
            return  # widget destroyed

        # Display a substring shifted by current position
        display_text = label.full_text[label.pos:] + label.full_text[:label.pos]
        label.config(text=display_text)
        label.pos = (label.pos + 1) % len(label.full_text)
        label.after(delay, scroll)

    scroll()

def get_line_style(line_name, styles_config):
    # Default style
    style = {"bg": "#122080", "fg": "white", "font_size": 27}

    # Match exact 3-digit number
    if line_name.isdigit() and len(line_name) == 3 and "3DIGIT" in styles_config:
        cfg = styles_config["3DIGIT"]
        style.update({
            "bg": cfg.get("bg", style["bg"]),
            "fg": cfg.get("fg", style["fg"]),
            "font_size": cfg.get("font_size", style["font_size"])
        })
        logging.debug("Line '{0}' matched 3DIGIT style: {1}".format(line_name, style))
        return style

    # Match keys in descending length (so 'ICE' gets checked before 'IC')
    for key in sorted(styles_config.keys(), key=lambda k: len(k), reverse=True):
        if key == "3DIGIT":
            continue
        if key in line_name:
            cfg = styles_config[key]
            style.update({
                "bg": cfg.get("bg", style["bg"]),
                "fg": cfg.get("fg", style["fg"]),
                "font_size": cfg.get("font_size", style["font_size"])
            })
            logging.debug("Line '{0}' matched style '{1}': {2}".format(line_name, key, style))
            return style

    # No match
    logging.debug("Line '{0}' did not match any style. Using default: {1}".format(line_name, style))
    return style


def fetch_departures(content_frame, config, root):
    global fetch_after_id, running, is_closing
    if not running or is_closing:
        return

    def fetch_in_thread():
        try:
            stop_id = config.get("stopId")
            req_base_url = config.get("reqBaseUrl")
            req_options = config.get("reqOptions", {})

            if stop_id is None or req_base_url is None:
                return

            url = req_base_url.format(stopId=stop_id)
            params = {k: str(v).lower() for k, v in req_options.items()}

            logging.info("Fetching departures from base URL {0} with params {1}".format(url, params))
            response = requests.get(url, params=params, timeout=10, verify="cacert.pem")
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            data = {"error": str(e)}

        def update_ui():
            if not running or is_closing:
                return
            clear_content(content_frame)

            if "error" in data:
                logging.error("An error occurred trying to fetch data: {0}".format(data["error"]))
                label = tk.Label(content_frame, text=FRONTEND_ERROR_MSG_NETWORK_ERROR_TEXT,
                                 fg="white", bg="#122080",
                                 font=("DB Neo Screen Sans Regular", 24),
                                 wraplength=content_frame.winfo_width() - 40)
                label.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)
            else:
                departures_list = data.get("departures", [])
                if not departures_list:
                    logging.info("No departures returned from API")
                    no_departures_label = tk.Label(
                        content_frame,
                        text=FRONTEND_ERROR_MSG_NO_DEPARTURES_TEXT,
                        fg="white",
                        bg="#122080",
                        font=("", 24),
                        wraplength=content_frame.winfo_width() - 40
                    )
                    no_departures_label.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)
                else:
                    logging.info("{0} departures retrieved from API".format(len(departures_list)))
                    screen_height = root.winfo_screenheight()
                    header_height = 80
                    row_height = 61
                    available_height = screen_height - header_height
                    max_rows = available_height // row_height

                    for i, departure in enumerate(departures_list[:max_rows]):
                        if not running or is_closing or not content_frame.winfo_exists():
                            break

                        element_frame = tk.Frame(content_frame, bg="#122080", height=60)
                        element_frame.pack_propagate(False)
                        element_frame.pack(fill=tk.X, pady=1)

                        line_name = departure.get("line", {}).get("name", "N/A")
                        destination_name = departure.get("destination", {}).get("name", "N/A")
                        platform_name = departure.get("platform")
                        raw_when = departure.get("when")

                        formatted_time = format_departure_time(raw_when)
                        main_fg_color = "white"
                        main_bg_color = "#122080"
                        time_fg_color = main_fg_color
                        time_font_weight = "normal"
                        time_font_size = 24
                        line_font_decoration = "bold"
                        destination_font_decoration = ""
                        platform_display_text = ""

                        style = get_line_style(line_name, config.get("LineStyles", {}))
                        line_label_bg = style.get("bg", main_bg_color)
                        line_label_fg = style.get("fg", main_fg_color)
                        line_font_size = style.get("font_size", 27)

                        is_cancelled = not raw_when or not platform_name
                        if is_cancelled:
                            formatted_time = ""
                            platform_display_text = ""
                        else:
                            platform_display_text = str(platform_name) if platform_name else ""

                        line_display_frame = tk.Frame(element_frame, bg=line_label_bg, width=100)
                        line_display_frame.pack_propagate(False)
                        line_display_frame.pack(side=tk.LEFT, fill=tk.Y)

                        line_label = tk.Label(line_display_frame, text=line_name, fg=line_label_fg, bg=line_label_bg,
                                              font=("DB Neo Screen Sans Bold", line_font_size, line_font_decoration))
                        line_label.pack(padx=5, pady=0, fill=tk.BOTH, expand=True)

                        line_display_frame.update_idletasks()
                        if line_label.winfo_reqwidth() > line_display_frame.winfo_width():
                            start_marquee(line_label, line_name)

                        destination_label = tk.Label(element_frame, text=destination_name,
                                                     fg=main_fg_color, bg=main_bg_color,
                                                     font=("DB Neo Screen Sans Regular", 24, destination_font_decoration))
                        destination_label.pack(side=tk.LEFT, padx=20, pady=(5, 0))

                        element_frame.update_idletasks()
                        if destination_label.winfo_reqwidth() > destination_label.winfo_width():
                            start_marquee(destination_label, destination_name)
                            spacer_frame = tk.Frame(element_frame, bg=main_bg_color)
                            spacer_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

                        time_label = tk.Label(element_frame, text=formatted_time, fg=time_fg_color, bg=main_bg_color,
                                              font=("DB Neo Screen Sans Regular", time_font_size, time_font_weight))
                        time_label.pack(side=tk.RIGHT, padx=20, pady=(5, 0))

                        if platform_display_text:
                            platform_label = tk.Label(element_frame, text=platform_display_text,
                                                      fg=main_fg_color, bg=main_bg_color,
                                                      font=("DB Neo Screen Sans Bold", 24))
                            platform_label.pack(side=tk.RIGHT, padx=20, pady=(5, 0))

            update_interval = config.get("updateInterval", 60)
            next_update_time = datetime.now() + timedelta(seconds=update_interval)
            fetch_after_id = root.after(update_interval * 1000,
                                        lambda: fetch_departures(content_frame, config, root))
            logging.info("Next update scheduled at {0}".format(
                next_update_time.strftime("%d.%m.%Y %H:%M:%S")))

        root.after(0, update_ui)
        
    threading.Thread(target=fetch_in_thread, daemon=True).start()

def main():
    global running, is_closing, clock_after_id, fetch_after_id
    global FRONTEND_ERROR_MSG_NO_DEPARTURES_TEXT, FRONTEND_ERROR_MSG_NETWORK_ERROR_TEXT
    global line_styles

    setup_logging()
    logging.info("Application initializing")

    root = tk.Tk()
    root.withdraw()

    load_font("fonts/DBNeoScreenSans-Regular.ttf")
    load_font("fonts/DBNeoScreenSans-Bold.ttf")

    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(0,
            u"Fehler beim Laden der Konfigurationsdatei:\n{0}".format(e),
            u"Fehler",
            0x10)
        sys.exit(1)
    
    line_styles = config.get("LineStyles", {})
    logging.info("Retrieved Line Styles from configuration file")
    
    root.deiconify()

    root.title("Novium")

    if config.get("fullscreen", True):
        root.attributes("-fullscreen", True)
    else:
        root.geometry("1024x768")

    root.configure(bg="#122080")

    if not config.get("showcursor", True):
        root.bind("<FocusIn>", lambda e: e.widget.config(cursor="none"))
        root.bind("<FocusOut>", lambda e: e.widget.config(cursor=""))
        root.bind("<Enter>", lambda e: e.widget.config(cursor="none"))
        root.bind("<Leave>", lambda e: e.widget.config(cursor=""))

    try:
        if os.path.exists("icon.ico"):
            root.iconbitmap("icon.ico")
    except Exception:
        pass

    header_bg_color = "#122080"
    top_header_frame = tk.Frame(root, bg=header_bg_color)
    top_header_frame.pack(side=tk.TOP, fill=tk.X)

    stop_sign_path = os.path.join(os.getcwd(), IMAGE_FOLDER, STOP_SIGN_IMAGE)
    stop_sign_photo = None
    if os.path.exists(stop_sign_path):
        try:
            logging.info("---- BEGIN LOADING OF IMAGE {0} ----".format(stop_sign_path))
            img = Image.open(stop_sign_path)
            img = img.resize((40, 40), Image.LANCZOS)
            stop_sign_photo = ImageTk.PhotoImage(img)
            root.stop_sign_photo = stop_sign_photo
            logging.info("---- END OF LOADING OF IMAGE {0} ----".format(stop_sign_path))
        except Exception:
            pass

    if stop_sign_photo:
        tk.Label(top_header_frame, image=stop_sign_photo, bg=header_bg_color).pack(side=tk.LEFT, padx=(20, 5), pady=10)

    frontend_errors = config.get("FrontendErrorMessages", {})
    logging.info("FrontendErrorMessages in config: %s", frontend_errors)
    
    if not isinstance(frontend_errors, dict):
        frontend_errors = {}
        logging.debug("FrontendErrorMessages not found or invalid, using empty dict")

    FRONTEND_ERROR_MSG_NO_DEPARTURES_TEXT = frontend_errors.get(
        "no_departures_text", no_departures_fallback_text
    )
    FRONTEND_ERROR_MSG_NETWORK_ERROR_TEXT = frontend_errors.get(
        "network_error", passenger_frontend_error_fallback_text
    )

    logging.debug("No Departures Text: %s", FRONTEND_ERROR_MSG_NO_DEPARTURES_TEXT)
    logging.debug("Network Error Text: %s", FRONTEND_ERROR_MSG_NETWORK_ERROR_TEXT)
    
    stop_name = config.get("stopName", "Stationsname nicht festgelegt")
    station_label = tk.Label(top_header_frame, text=stop_name, fg="white", bg=header_bg_color, font=("DB Neo Screen Sans Bold", 24))
    station_label.pack(side=tk.LEFT, padx=(0, 20), pady=10)

    clock_frame = tk.Frame(top_header_frame, bg=header_bg_color)
    clock_frame.pack(side=tk.RIGHT, padx=20, pady=10)

    hour_label = tk.Label(clock_frame, text="", fg="white", bg=header_bg_color, font=("DB Neo Screen Sans Bold", 24))
    hour_label.pack(side=tk.LEFT)

    colon_label = tk.Label(clock_frame, text=":", fg="white", bg=header_bg_color, font=("DB Neo Screen Sans Bold", 24))
    colon_label.pack(side=tk.LEFT)

    minute_label = tk.Label(clock_frame, text="", fg="white", bg=header_bg_color, font=("DB Neo Screen Sans Bold", 24))
    minute_label.pack(side=tk.LEFT)

    toggle_colon_visibility = [True]
    update_clock(hour_label, colon_label, minute_label, toggle_colon_visibility, header_bg_color)

    content_frame = tk.Frame(root, bg="#122080")
    content_frame.pack(expand=True, fill=tk.BOTH)

    fetch_departures(content_frame, config, root)

    def on_closing():
        global running, is_closing
        is_closing = True
        running = False

        safe_after_cancel(root, clock_after_id)
        safe_after_cancel(root, fetch_after_id)

        logging.info("Application closing")

        # Call root.quit() to stop mainloop immediately and avoid further callbacks
        try:
            root.quit()
        except Exception:
            pass

        # Destroy root safely after a short delay
        root.after(50, root.destroy)

    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()


if __name__ == "__main__":
    main()
