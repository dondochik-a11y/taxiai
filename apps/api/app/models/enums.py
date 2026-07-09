import enum

from sqlalchemy import Enum as SqlEnum


def pg_enum(enum_cls: type[enum.Enum], name: str) -> SqlEnum:
    """Build a Postgres ENUM column type that stores each member's .value
    (e.g. 'petrol92') rather than SQLAlchemy's default of .name (e.g. 'PETROL_92')."""
    return SqlEnum(enum_cls, name=name, values_callable=lambda cls: [e.value for e in cls])


class TariffPlan(str, enum.Enum):
    ECONOMY = "economy"
    COMFORT = "comfort"
    COMFORT_PLUS = "comfort_plus"
    BUSINESS = "business"


class FuelType(str, enum.Enum):
    PETROL_92 = "petrol92"
    PETROL_95 = "petrol95"
    DIESEL = "diesel"
    GAS = "gas"
    ELECTRIC = "electric"


class DataSource(str, enum.Enum):
    SYNTHETIC = "synthetic"
    LIVE = "live"
    MANUAL = "manual"
    RADAR = "radar"  # lifted from a driver's kef-radar screenshot


class PrecipitationType(str, enum.Enum):
    NONE = "none"
    RAIN = "rain"
    SNOW = "snow"
    SLEET = "sleet"


class CalendarEventType(str, enum.Enum):
    PUBLIC_HOLIDAY = "public_holiday"
    WEEKEND = "weekend"
    CONCERT = "concert"
    FOOTBALL_MATCH = "football_match"
    MASS_EVENT = "mass_event"


class ImpactLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AirportCode(str, enum.Enum):
    SVO = "SVO"
    DME = "DME"
    VKO = "VKO"


class FlightDirection(str, enum.Enum):
    ARRIVAL = "arrival"
    DEPARTURE = "departure"


class FlightStatus(str, enum.Enum):
    ON_TIME = "on_time"
    DELAYED = "delayed"
    CANCELLED = "cancelled"
    LANDED = "landed"


class MetroIncidentType(str, enum.Enum):
    CLOSURE = "closure"
    REPAIR = "repair"
    DELAY = "delay"
    INCIDENT = "incident"


class RecommendationAction(str, enum.Enum):
    STAY = "stay"
    MOVE = "move"


class DeliveryChannel(str, enum.Enum):
    WEB = "web"
    TELEGRAM = "telegram"


class ExpenseCategory(str, enum.Enum):
    WASH = "wash"
    FINE = "fine"
    OTHER = "other"


class ChatRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class NotificationType(str, enum.Enum):
    MORNING_PLAN = "morning_plan"
    PRESHIFT_ALERT = "preshift_alert"
    POSTSHIFT_SUMMARY = "postshift_summary"
