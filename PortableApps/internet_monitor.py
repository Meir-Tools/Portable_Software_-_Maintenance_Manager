import time
import socket
from datetime import datetime

# הגדרות
CHECK_INTERVAL = 5  # כל כמה שניות לבדוק את החיבור
LOG_FILE = "internet_log.txt"  # שם קובץ הלוג שיקלטו אליו הנתונים
TARGET_SERVER = "1.1.1.1"  # השרת מולו בודקים (  DNS)

def is_connected():
    """פונקציה שבודקת האם יש חיבור לאינטרנט"""
    try:
        # מנסה לפתוח חיבור מהיר לשרת בפורט 53 (DNS)
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((TARGET_SERVER, 53))
        return True
    except socket.error:
        return False

def write_to_log(message):
    """פונקציה שרושמת את האירוע בקובץ הלוג עם חותמת זמן"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}\n"
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line)
    print(log_line.strip()) # מדפיס גם למסך שתוכל לראות בזמן אמת

def monitor_internet():
    print(f"התחלת ניטור אינטרנט. הלוג יישמר בקובץ: {LOG_FILE}")
    write_to_log("השירות הופעל - מתחיל בניטור.")
    
    was_connected = True  # מצב קודם (מניחים שהיה מחובר בהתחלה)

    while True:
        currently_connected = is_connected()

        # מקרה 1: האינטרנט התנתק עכשיו
        if was_connected and not currently_connected:
            write_to_log("חיבור האינטרנט אבד! ❌")
            was_connected = False

        # מקרה 2: האינטרנט חזר
        elif not was_connected and currently_connected:
            write_to_log("חיבור האינטרנט חזר!  🟢")
            was_connected = True

        # המתן לפני הבדיקה הבאה
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        monitor_internet()
    except KeyboardInterrupt:
        write_to_log("השירות הופסק על ידי המשתמש.")
        print("\nהניטור הופסק.")