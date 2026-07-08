"""Named, documented constants for the synthetic data generator's injected signals.

These are the "ground truth" effects that app/ml/pattern_mining.py should
approximately rediscover from the generated data — a rough self-check that the
pattern-mining pipeline actually finds real structure, not noise.
"""

RANDOM_SEED = 20260101

BACKFILL_DAYS = 90
# Native 5-min resolution only for the most recent N days (keeps row counts sane);
# hourly resolution for the remainder of the backfill window.
HIGH_RES_RECENT_DAYS = 14

# Districts (by name, matching packages/shared/constants/moscow_districts.json)
# where rain/snow boosts demand more than the city-wide average — these sit near
# major train stations, so bad weather pushes more people to hail a ride.
RAIN_BOOST_DISTRICTS = ["Павелецкая", "Курская"]
RAIN_BOOST_MULTIPLIER = 1.27  # reproduces the spec's own "+27%" example

AIRPORT_DISTRICTS = ["Шереметьевская", "Внуково", "Домодедово"]
AIRPORT_ARRIVAL_WINDOW_MINUTES = 45  # look-back window for "recent arrivals" demand bump
AIRPORT_ARRIVAL_DEMAND_WEIGHT = 0.35  # max demand_level contribution from arrival density

# Event district: nearest seeded district to Luzhniki stadium.
EVENT_DISTRICT = "Хамовники"
EVENT_DEMAND_BOOST = 0.6  # additive demand_level bump within the event window
EVENT_WINDOW_HOURS = 2  # +/- hours around a football/concert calendar_event

CENTER_DISTRICTS = ["Тверской", "Арбат", "Замоскворечье", "Пресненский", "Хамовники", "Дорогомилово"]
FRIDAY_LATE_HOUR = 22
FRIDAY_CENTER_DISCOUNT = 0.75  # center demand *= this factor, Fri 22:00+
FRIDAY_AIRPORT_BOOST = 1.2  # airport demand *= this factor, Fri 22:00+

# Base hourly demand curve, bimodal rush hours (index = hour 0-23), 0..1 scale before
# multipliers/noise are applied.
HOURLY_BASE_DEMAND = [
    0.25, 0.18, 0.12, 0.10, 0.10, 0.15,  # 00-05
    0.30, 0.55, 0.80, 0.70, 0.45, 0.40,  # 06-11
    0.45, 0.42, 0.40, 0.45, 0.55, 0.75,  # 12-17
    0.85, 0.70, 0.55, 0.50, 0.45, 0.35,  # 18-23
]

# Day-of-week multiplier, Monday=0 .. Sunday=6
DOW_MULTIPLIER = {
    0: 1.00,  # Mon
    1: 1.00,  # Tue
    2: 1.02,  # Wed
    3: 1.05,  # Thu
    4: 1.20,  # Fri night lift handled separately too
    5: 1.25,  # Sat
    6: 0.85,  # Sun (esp. mornings, handled via extra dampener below)
}
SUNDAY_MORNING_DAMPENER = 0.6  # applied Sun 06:00-12:00 on top of DOW_MULTIPLIER

# Russian public holidays (month, day) — fixed-date only, good enough for MVP.
FIXED_RUSSIAN_HOLIDAYS = [
    (1, 1), (1, 2), (1, 7),  # New Year / Orthodox Christmas
    (2, 23),  # Defender of the Fatherland Day
    (3, 8),  # International Women's Day
    (5, 1), (5, 9),  # Spring/Labour Day, Victory Day
    (6, 12),  # Russia Day
    (11, 4),  # Unity Day
]

# Noise
DEMAND_NOISE_STD = 0.06
TRIP_PRICE_NOISE_STD = 0.15  # relative
