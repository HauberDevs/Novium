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
from modules.utils.luacfgparser import parse_lua_cfg as cfgparse

APP_VERSION = "2.0"
CONFIG_FILE = "novium.cfg"
LOGS_FOLDER_NAME = "logs"
IMAGE_FOLDER = "images"

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
    label.full_text = text + "    "  # Add spaces for smooth scrolling
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

    def map_field(departure, mapping, field_name, default=None):
        path = mapping.get(field_name) if mapping else None

        if path:
            parts = path.split(".")
            current = departure
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = None
                    break
            if current is not None:
                return current

        if field_name == "line":
            return departure.get("line", {}).get("name", "N/A")
        elif field_name == "destination":
            return departure.get("destination", {}).get("name", "N/A")
        elif field_name == "time":
            return departure.get("when") or departure.get("plannedWhen")
        elif field_name == "platform":
            return departure.get("platform") or departure.get("plannedPlatform")
        elif field_name == "cancelled":
            return departure.get("cancelled", False)

        return default

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
                label = tk.Label(content_frame, text=passenger_frontend_error_fallback_text,
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
                        text=no_departures_fallback_text,
                        fg="white",
                        bg="#122080",
                        font=("", 24),
                        wraplength=content_frame.winfo_width() - 40
                    )
                    no_departures_label.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)
                else:
                    def minutes_to_departure(dep):
                        when = map_field(dep, mapping, "time")
                        try:
                            if not when:
                                return 99999
                            dt = datetime.strptime(when[:19], "%Y-%m-%dT%H:%M:%S")
                            diff = (dt - datetime.now()).total_seconds() / 60.0
                            return diff if diff > 0 else 0
                        except Exception:
                            return 99999

                    mapping = config.get("CustomResponseMapping", {})
                    departures_list.sort(key=minutes_to_departure)

                    logging.info("{0} departures retrieved from API".format(len(departures_list)))

                    if config.get("fullscreen", True):
                        height_ref = root.winfo_screenheight()
                    else:
                        height_ref = root.winfo_height()

                    header_height = 80
                    row_height = 61
                    available_height = height_ref - header_height
                    max_rows = available_height // row_height - 1

                    for i, departure in enumerate(departures_list[:max_rows]):
                        if not running or is_closing or not content_frame.winfo_exists():
                            break

                        element_frame = tk.Frame(content_frame, bg="#122080", height=60)
                        element_frame.pack_propagate(False)
                        element_frame.pack(fill=tk.X, pady=1)

                        line_name = map_field(departure, mapping, "line")
                        destination_name = map_field(departure, mapping, "destination")
                        raw_when = map_field(departure, mapping, "time")
                        platform_name = map_field(departure, mapping, "platform")
                        cancelled = map_field(departure, mapping, "cancelled")

                        if cancelled:
                            formatted_time = "Fahrt fällt aus"
                            platform_display_text = ""
                            time_fg_color = "red"
                            time_font_weight = "bold"
                        else:
                            formatted_time = format_departure_time(raw_when)
                            platform_display_text = str(platform_name) if platform_name else ""
                            time_fg_color = "white"
                            time_font_weight = "normal"

                        main_fg_color = "white"
                        main_bg_color = "#122080"
                        line_font_decoration = "bold"
                        destination_font_decoration = ""

                        style = get_line_style(line_name, config.get("LineStyles", {}))
                        line_label_bg = style.get("bg", main_bg_color)
                        line_label_fg = style.get("fg", main_fg_color)
                        line_font_size = style.get("font_size", 27)

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
                                              font=("DB Neo Screen Sans Regular", 24, time_font_weight))
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
    global passenger_frontend_error_fallback_text, no_departures_fallback_text
    global line_styles
    global scale

    def get_scale_factor(root, base_width=1024, base_height=768):
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        scale_w = screen_width / base_width
        scale_h = screen_height / base_height
        return min(scale_w, scale_h)

    setup_logging()
    logging.info("Application initializing")

    root = tk.Tk()
    root.withdraw()

    load_font("fonts/DBNeoScreenSans-Regular.ttf")
    load_font("fonts/DBNeoScreenSans-Bold.ttf")

    scale = get_scale_factor(root)

    try:
        with open(CONFIG_FILE, "r") as f:
            config = cfgparse(CONFIG_FILE)
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

    logo_path = config.get("LogoImage")
    db_logo_image = None

    if logo_path:
        abs_logo_path = os.path.abspath(logo_path)
        logging.info("Configured logo path: {0}".format(abs_logo_path))

        if os.path.exists(abs_logo_path):
            try:
                logging.info("---- BEGIN LOADING OF IMAGE {0} ----".format(abs_logo_path))
                img = Image.open(abs_logo_path)

                # Scaling
                orig_width, orig_height = img.size
                max_size = int(40 * scale * 1.6)
                if orig_width > orig_height:
                    new_width = max_size
                    new_height = int(orig_height * (max_size / orig_width))
                else:
                    new_height = max_size
                    new_width = int(orig_width * (max_size / orig_height))

                img = img.resize((new_width, new_height), Image.LANCZOS)
                db_logo_image = ImageTk.PhotoImage(img)
                root.db_logo_image = db_logo_image
                logging.info("---- END OF LOADING OF IMAGE {0} ----".format(abs_logo_path))
            except Exception as e:
                logging.error("Failed to load logo image: {0}".format(e))
        else:
            logging.warning("Logo path configured but file does not exist: {0}".format(abs_logo_path))
    else:
        logging.warning("No LogoImage configured in the config file.")
        
    # Configure grid layout with 3 columns for the header
    top_header_frame.columnconfigure(0, weight=1)
    top_header_frame.columnconfigure(1, weight=1)
    top_header_frame.columnconfigure(2, weight=1)

    # Left frame for stop sign and station label
    left_frame = tk.Frame(top_header_frame, bg=header_bg_color)
    left_frame.grid(row=0, column=0, sticky="w", padx=20, pady=10)

    if db_logo_image:
        tk.Label(left_frame, image=db_logo_image, bg=header_bg_color).pack(side=tk.LEFT, padx=(0, 5))

    center_frame = tk.Frame(top_header_frame, bg=header_bg_color)
    center_frame.grid(row=0, column=1)

    # Determine header text based on config type
    display_type = config.get("type", "departures").lower()
    if display_type == "arrivals":
        german_text = "Ankünfte"
        english_text = "Arrivals"
    elif display_type == "departures":
        german_text = "Abfahrten"
        english_text = "Departures"
    else:
        # fallback if config type invalid
        german_text = "Abfahrten"
        english_text = "Departures"

    abfahrten_label = tk.Label(
        center_frame,
        text=german_text,
        fg="white",
        bg=header_bg_color,
        font=("DB Neo Screen Sans Bold", 24),
    )
    abfahrten_label.pack(side=tk.LEFT)

    departures_label = tk.Label(
        center_frame,
        text=english_text,
        fg="white",
        bg=header_bg_color,
        font=("DB Neo Screen Sans Regular", 20, "italic"),
    )
    departures_label.pack(side=tk.LEFT, padx=(5,0))

    # Right frame for clock
    clock_frame = tk.Frame(top_header_frame, bg=header_bg_color)
    clock_frame.grid(row=0, column=2, sticky="e", padx=20, pady=10)

    hour_label = tk.Label(clock_frame, text="", fg="white", bg=header_bg_color, font=("DB Neo Screen Sans Bold", 24))
    hour_label.pack(side=tk.LEFT)

    colon_label = tk.Label(clock_frame, text=":", fg="white", bg=header_bg_color, font=("DB Neo Screen Sans Bold", 24))
    colon_label.pack(side=tk.LEFT)

    minute_label = tk.Label(clock_frame, text="", fg="white", bg=header_bg_color, font=("DB Neo Screen Sans Bold", 24))
    minute_label.pack(side=tk.LEFT)

    toggle_colon_visibility = [True]
    update_clock(hour_label, colon_label, minute_label, toggle_colon_visibility, header_bg_color)

    # --- Header Labels Section ---
    header_labels_frame = tk.Frame(root, bg="#122080")
    header_labels_frame.pack(fill=tk.X)

    header_labels_frame.columnconfigure(0, weight=0)  # Line
    header_labels_frame.columnconfigure(1, weight=1)  # Destination (expands)
    header_labels_frame.columnconfigure(2, weight=0)  # Platform
    header_labels_frame.columnconfigure(3, weight=0)  # Arrival

    def create_dual_language_label(parent, german, english, anchor="w", justify="left", padx=(5, 5)):
        frame = tk.Frame(parent, bg="#122080")

        german_label = tk.Label(
            frame,
            text=german,
            font=("DB Neo Screen Sans Bold", int(20 * scale)),
            fg="white",
            bg="#122080",
            anchor=anchor,
            justify=justify
        )   
        german_label.pack(anchor=anchor)

        english_label = tk.Label(
            frame,
            text=english,
            font=("DB Neo Screen Sans Regular", int(16 * scale), "italic"),
            fg="white",
            bg="#122080",
            anchor=anchor,
            justify=justify
        )
        english_label.pack(anchor=anchor)
        
        return frame

    line_header = create_dual_language_label(
        header_labels_frame, "Linie", "Line",
        anchor="center", justify="left", padx=(10, 5)
    )
    line_header.grid(row=0, column=0, sticky="w", padx=(10, 5))

    destination_header = create_dual_language_label(
        header_labels_frame, "Ziel", "Destination",
        anchor="w", justify="center"
    )
    destination_header.config(width=50)  # Adjust width as needed
    destination_header.grid(row=0, column=1, sticky="nw", padx=(5, 5))
    destination_header.place(x=120)

    platform_header = create_dual_language_label(
        header_labels_frame, "Gleis", "Platform",
        anchor="e", justify="right"
    )
    platform_header.config(width=10)  # Adjust width as needed
    platform_header.grid(row=0, column=2, sticky="e", padx=(5, 15))

    arrival_header = create_dual_language_label(
        header_labels_frame, "Geplant", "Scheduled",
        anchor="e", justify="right"
    )
    arrival_header.grid(row=0, column=3, sticky="e", padx=(5, 10))
    # --- End Header Labels Section ---

    separator = tk.Frame(root, bg="white", height=2)
    separator.pack(fill=tk.X, pady=(2, 2))
    
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

        try:
            root.quit()
        except Exception:
            pass

        root.after(50, root.destroy)

    root.protocol("WM_DELETE_WINDOW", on_closing)

    root.mainloop()


if __name__ == "__main__":
    main()
