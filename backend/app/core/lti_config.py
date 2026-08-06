import os
import json
from pylti1p3.tool_config import ToolConfigDict

def get_lti_config():
    """
    Конфигурация LTI 1.3 Tool.
    В реальном проекте ключи и client_id должны храниться в БД или Vault.
    """
     
    config = {
        "moodle_platform": {
            "client_id": os.getenv("LTI_CLIENT_ID", "moodle_hackathon_client"),
            "auth_login_url": os.getenv("LTI_AUTH_LOGIN_URL", "https://moodle.example.com/mod/lti/auth.php"),
            "auth_token_url": os.getenv("LTI_AUTH_TOKEN_URL", "https://moodle.example.com/mod/lti/token.php"),
            "key_set_url": os.getenv("LTI_KEY_SET_URL", "https://moodle.example.com/mod/lti/keyset.php"),
            "private_key_file": os.getenv("LTI_PRIVATE_KEY_PATH", "/app/certs/lti_private.key"),
            "public_key_file": os.getenv("LTI_PUBLIC_KEY_PATH", "/app/certs/lti_public.key"),
            "deployment_ids": os.getenv("LTI_DEPLOYMENT_IDS", "[\"1\"]")
        }
    }
    
     
    try:
        with open(config["moodle_platform"]["private_key_file"], "r") as f:
            private_key = f.read()
        with open(config["moodle_platform"]["public_key_file"], "r") as f:
            public_key = f.read()
    except FileNotFoundError:
         
        private_key = "---BEGIN RSA PRIVATE KEY---\n..."
        public_key = "---BEGIN PUBLIC KEY---\n..."

    tool_config = ToolConfigDict()
    for issuer, data in config.items():
        tool_config.set_key(issuer, private_key)
        tool_config.set_public_key(issuer, public_key)
        tool_config.set_client_id(issuer, data["client_id"])
        tool_config.set_auth_login_url(issuer, data["auth_login_url"])
        tool_config.set_auth_token_url(issuer, data["auth_token_url"])
        tool_config.set_key_set_url(issuer, data["key_set_url"])
        tool_config.set_deployment_ids(issuer, json.loads(data["deployment_ids"]))

    return tool_config
