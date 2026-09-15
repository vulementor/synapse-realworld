from enum import StrEnum


class ProductType(StrEnum):
    TOWNHOUSE = "townhouse"
    GARDEN_TOWNHOUSE = "garden_townhouse"
    STREET_VILLA = "street_villa"
    GARDEN_VILLA = "garden_villa"
    SHOPHOUSE = "shophouse"


class InventoryState(StrEnum):
    AVAILABLE = "available"
    HELD = "held"
    BOOKED = "booked"
    SOLD = "sold"
    BLOCKED = "blocked"


class PurchasePurpose(StrEnum):
    OWN_STAY = "own_stay"
    INVESTMENT = "investment"
    MIXED = "mixed"
    BUSINESS = "business"
    UNKNOWN = "unknown"


class DecisionStage(StrEnum):
    INITIAL_INTEREST = "initial_interest"
    QUALIFIED = "qualified"
    SHORTLIST = "shortlist"
    SITE_TOUR = "site_tour"
    NEGOTIATION = "negotiation"
    BOOKING = "booking"
    FINAL = "final"


class OutsideOption(StrEnum):
    COMPETITOR_PROJECT = "competitor_project"
    LAND_HOUSE = "land_house"
    CONTINUE_RENTING = "continue_renting"
    POSTPONED = "postponed"
    NO_PURCHASE = "no_purchase"


class ChoiceOutcome(StrEnum):
    SELECTED_LAA_UNIT = "selected_laa_unit"
    SELECTED_COMPETITOR = "selected_competitor"
    SELECTED_LAND_HOUSE = "selected_land_house"
    CONTINUE_RENTING = "continue_renting"
    POSTPONED = "postponed"
    NO_PURCHASE = "no_purchase"
    UNRESOLVED = "unresolved"


class ReasonDirection(StrEnum):
    MOTIVATOR = "motivator"
    OBJECTION = "objection"


class ReasonCode(StrEnum):
    PRICE = "price"
    MONTHLY_CASHFLOW = "monthly_cashflow"
    FINANCING = "financing"
    COMMUTE = "commute"
    LOCATION_PERCEPTION = "location_perception"
    PRODUCT_SIZE = "product_size"
    PRODUCT_LAYOUT = "product_layout"
    PRODUCT_TYPE = "product_type"
    PARK_GREEN_SPACE = "park_green_space"
    SECURITY = "security"
    CHILD_AMENITY = "child_amenity"
    SCHOOL = "school"
    COMMERCIAL_POTENTIAL = "commercial_potential"
    RENTAL_YIELD = "rental_yield"
    LIQUIDITY_RESALE = "liquidity_resale"
    LEGAL_TRUST = "legal_trust"
    DEVELOPER_TRUST = "developer_trust"
    HANDOVER_READINESS = "handover_readiness"
    SPOUSE_FAMILY = "spouse_family"
    TIMING = "timing"
    COMPETITOR = "competitor"
    MARKET_UNCERTAINTY = "market_uncertainty"
    SALES_EXPERIENCE = "sales_experience"
    UNKNOWN = "unknown"
