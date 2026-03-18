from app.database import database
import bcrypt

class AuthService:
    def login(self, email: str, password: str) -> tuple[bool, str]:
        return database.verify_user(email, password)

    def register(self, name: str, email: str, password: str, **kwargs) -> tuple[bool, str]:
        return database.create_user(name, email, password, **kwargs)

    def verify_audio_password(self, spoken_word: str) -> tuple[bool, str, str]:
        return database.verify_audio(spoken_word)

    def get_user_by_email(self, email: str) -> dict | None:
        return database.get_user_by_email(email)

    def get_credentials(self, email: str) -> dict | None:
        return database.get_user_credentials(email)
    
    def generate_pins(self, tg_included: bool = False) -> dict:
        return database.generate_pins(tg_included)
    
    def store_pins(self, email: str, gmail_pin: str, telegram_pin: str) -> tuple[bool, str]:
        return database.store_pins(email, gmail_pin, telegram_pin)

    def verify_pin(self, email: str, service: str, pin: str) -> bool:
        return database.verify_pin(email, service, pin)
    
    def is_admin(self, email: str) -> bool:
        return database.is_admin(email)

    def add_admin(self, email: str) -> tuple[bool, str]:
        return database.add_admin(email)

auth_service = AuthService()
