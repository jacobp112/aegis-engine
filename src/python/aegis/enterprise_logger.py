import logging
import logging.handlers
import json
import os

# --- ENTERPRISE LOGGER ---
class EnterpriseLogger:
    def __init__(self, name="AegisAudit"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # 1. Syslog Handler (UDP 514) - For Splunk/SIEM
        syslog_host = os.environ.get("AEGIS_SYSLOG_HOST", "localhost")
        try:
            handler = logging.handlers.SysLogHandler(address=(syslog_host, 514))
            formatter = logging.Formatter('%(asctime)s AEGIS_AUDIT: %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        except Exception as e:
            print(f"[LOG] Syslog unavailable: {e}")

        # 2. File Handler (Fallback)
        file_handler = logging.FileHandler("aegis_audit.jsonl")
        self.logger.addHandler(file_handler)

    def log(self, event: dict):
        msg = json.dumps(event)
        self.logger.info(msg)

# Used by AI Bridge
audit_logger = EnterpriseLogger()
