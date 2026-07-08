from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models here so Alembic's autogenerate and Base.metadata.create_all
# can discover every table through this single module.
from app.models.user import User, DriverProfile  # noqa: E402,F401
from app.models.district import District  # noqa: E402,F401
from app.models.demand import DemandSnapshot  # noqa: E402,F401
from app.models.trip import Trip  # noqa: E402,F401
from app.models.weather import WeatherObservation  # noqa: E402,F401
from app.models.traffic import TrafficObservation  # noqa: E402,F401
from app.models.calendar import CalendarEvent  # noqa: E402,F401
from app.models.airport import AirportFlight  # noqa: E402,F401
from app.models.metro import MetroIncident  # noqa: E402,F401
from app.models.ai_analysis import AiTripAnalysis  # noqa: E402,F401
from app.models.forecast import Forecast  # noqa: E402,F401
from app.models.recommendation import Recommendation  # noqa: E402,F401
from app.models.pattern_insight import PatternInsight  # noqa: E402,F401
from app.models.finance import FinanceSummary, Expense  # noqa: E402,F401
from app.models.chat import ChatMessage  # noqa: E402,F401
from app.models.notification import TelegramNotificationLog  # noqa: E402,F401
from app.models.pricing import PriceObservation  # noqa: E402,F401
