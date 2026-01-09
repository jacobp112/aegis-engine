import time
import random
import threading
from digital_analyst import trigger_investigation_async

class PKYC_Feed:
    def __init__(self):
        self.running = False

    def start_feed(self):
        self.running = True
        print("[pKYC] 📡 Live Feed Connected: Companies House, Equifax, Dow Jones.")
        t = threading.Thread(target=self._feed_loop)
        t.daemon = True
        t.start()

    def stop_feed(self):
        self.running = False

    def _feed_loop(self):
        events = [
            ("Director Change", "Corporate Structure Risk"),
            ("Credit Score Drop", "Financial Distress"),
            ("Address Change", "Geographic Risk"),
            ("New Sanction", "Sanctions Hit")
        ]

        entities = ["Shell Corp Ltd", "Mule Account 01", "John Doe", "Tech Solutions Inc"]

        while self.running:
            # Randomly trigger an event every 5-10 seconds
            time.sleep(random.randint(5, 10))

            event, risk_type = random.choice(events)
            entity = random.choice(entities)
            case_id = random.randint(10000, 99999)

            print(f"\n[pKYC] 🚨 ALERT: {event} for '{entity}'")
            print(f"[pKYC] Triggering Digital Analyst due to: {risk_type}")

            # Trigger the Agent
            trigger_investigation_async(case_id, entity, risk_type)

if __name__ == "__main__":
    feed = PKYC_Feed()
    feed.start_feed()

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        feed.stop_feed()
