"""Entity dictionaries and matching (REQ-NEWS-005). Hand-made lists of names that matter for air freight and
shipping; they are not exhaustive. A name that is not in a list is simply not extracted: nothing is guessed,
and an event without a recognised place keeps geographic_scope UNKNOWN."""
import re

# name or alias (lower case) -> (ISO 3166-1 alpha-2, region)
COUNTRIES = {
    "china": ("CN", "ASIA"), "chinese": ("CN", "ASIA"), "hong kong": ("HK", "ASIA"), "taiwan": ("TW", "ASIA"), "japan": ("JP", "ASIA"), "japanese": ("JP", "ASIA"),
    "south korea": ("KR", "ASIA"), "north korea": ("KP", "ASIA"), "korea": ("KR", "ASIA"), "korean": ("KR", "ASIA"), "vietnam": ("VN", "ASIA"), "thailand": ("TH", "ASIA"), "malaysia": ("MY", "ASIA"),
    "singapore": ("SG", "ASIA"), "indonesia": ("ID", "ASIA"), "philippines": ("PH", "ASIA"), "india": ("IN", "SOUTH_ASIA"),
    "pakistan": ("PK", "SOUTH_ASIA"), "bangladesh": ("BD", "SOUTH_ASIA"), "sri lanka": ("LK", "SOUTH_ASIA"), "nepal": ("NP", "SOUTH_ASIA"),
    "iran": ("IR", "MIDDLE_EAST"), "iranian": ("IR", "MIDDLE_EAST"), "israel": ("IL", "MIDDLE_EAST"), "israeli": ("IL", "MIDDLE_EAST"), "iraq": ("IQ", "MIDDLE_EAST"),
    "saudi arabia": ("SA", "MIDDLE_EAST"), "saudi": ("SA", "MIDDLE_EAST"), "qatar": ("QA", "MIDDLE_EAST"), "bahrain": ("BH", "MIDDLE_EAST"), "kuwait": ("KW", "MIDDLE_EAST"),
    "oman": ("OM", "MIDDLE_EAST"), "yemen": ("YE", "MIDDLE_EAST"), "lebanon": ("LB", "MIDDLE_EAST"), "syria": ("SY", "MIDDLE_EAST"), "jordan": ("JO", "MIDDLE_EAST"),
    "united arab emirates": ("AE", "MIDDLE_EAST"), "turkey": ("TR", "MIDDLE_EAST"), "turkiye": ("TR", "MIDDLE_EAST"), "egypt": ("EG", "MIDDLE_EAST"),
    "russia": ("RU", "EUROPE"), "russian": ("RU", "EUROPE"), "ukraine": ("UA", "EUROPE"), "ukrainian": ("UA", "EUROPE"), "belarus": ("BY", "EUROPE"),
    "germany": ("DE", "EUROPE"), "german": ("DE", "EUROPE"), "france": ("FR", "EUROPE"), "french": ("FR", "EUROPE"), "netherlands": ("NL", "EUROPE"), "dutch": ("NL", "EUROPE"),
    "belgium": ("BE", "EUROPE"), "luxembourg": ("LU", "EUROPE"), "italy": ("IT", "EUROPE"), "spain": ("ES", "EUROPE"), "poland": ("PL", "EUROPE"), "greece": ("GR", "EUROPE"),
    "united kingdom": ("GB", "EUROPE"), "britain": ("GB", "EUROPE"), "british": ("GB", "EUROPE"), "ireland": ("IE", "EUROPE"), "switzerland": ("CH", "EUROPE"),
    "sweden": ("SE", "EUROPE"), "norway": ("NO", "EUROPE"), "denmark": ("DK", "EUROPE"), "finland": ("FI", "EUROPE"), "austria": ("AT", "EUROPE"), "portugal": ("PT", "EUROPE"),
    "united states": ("US", "NORTH_AMERICA"), "american": ("US", "NORTH_AMERICA"), "canada": ("CA", "NORTH_AMERICA"), "canadian": ("CA", "NORTH_AMERICA"),
    "mexico": ("MX", "NORTH_AMERICA"), "brazil": ("BR", "LATIN_AMERICA"), "argentina": ("AR", "LATIN_AMERICA"), "chile": ("CL", "LATIN_AMERICA"), "colombia": ("CO", "LATIN_AMERICA"),
    "peru": ("PE", "LATIN_AMERICA"), "panama": ("PA", "LATIN_AMERICA"), "venezuela": ("VE", "LATIN_AMERICA"), "south africa": ("ZA", "AFRICA"), "nigeria": ("NG", "AFRICA"),
    "kenya": ("KE", "AFRICA"), "ethiopia": ("ET", "AFRICA"), "sudan": ("SD", "AFRICA"), "libya": ("LY", "AFRICA"), "morocco": ("MA", "AFRICA"), "australia": ("AU", "OCEANIA"),
    "new zealand": ("NZ", "OCEANIA"),
}
# acronyms are matched case-sensitively on the original headline
COUNTRY_ACRONYMS = {"US": ("US", "NORTH_AMERICA"), "U.S.": ("US", "NORTH_AMERICA"), "USA": ("US", "NORTH_AMERICA"), "UK": ("GB", "EUROPE"), "UAE": ("AE", "MIDDLE_EAST")}
REGIONS = {
    "middle east": "MIDDLE_EAST", "persian gulf": "MIDDLE_EAST", "arabian gulf": "MIDDLE_EAST", "europe": "EUROPE", "european": "EUROPE", "asia": "ASIA", "asian": "ASIA", "asia pacific": "ASIA",
    "asia-pacific": "ASIA", "south asia": "SOUTH_ASIA", "southeast asia": "ASIA", "north america": "NORTH_AMERICA", "transpacific": "TRANSPACIFIC", "trans-pacific": "TRANSPACIFIC",
    "transatlantic": "TRANSATLANTIC", "trans-atlantic": "TRANSATLANTIC", "africa": "AFRICA", "african": "AFRICA", "latin america": "LATIN_AMERICA", "south america": "LATIN_AMERICA",
    "black sea": "BLACK_SEA", "baltic": "BALTIC",
}
REGION_ACRONYMS = {"EU": "EUROPE", "APAC": "ASIA"}
# sea areas and chokepoints: always maritime
CHOKEPOINTS = {
    "suez canal": "SUEZ_CANAL", "suez": "SUEZ_CANAL", "red sea": "RED_SEA", "bab el-mandeb": "BAB_EL_MANDEB", "bab-el-mandeb": "BAB_EL_MANDEB", "bab el mandeb": "BAB_EL_MANDEB",
    "gulf of aden": "GULF_OF_ADEN", "strait of hormuz": "STRAIT_OF_HORMUZ", "hormuz": "STRAIT_OF_HORMUZ", "panama canal": "PANAMA_CANAL", "malacca": "STRAIT_OF_MALACCA",
    "bosphorus": "BOSPHORUS", "cape of good hope": "CAPE_OF_GOOD_HOPE", "taiwan strait": "TAIWAN_STRAIT", "south china sea": "SOUTH_CHINA_SEA",
}
# places that are a port, an airport or both; the role is decided from the headline (see extract)
PORT_PLACES = {
    "shanghai", "ningbo", "shenzhen", "yantian", "qingdao", "tianjin", "guangzhou", "singapore", "rotterdam", "antwerp", "hamburg", "bremerhaven", "los angeles", "long beach",
    "new york", "savannah", "felixstowe", "jebel ali", "colombo", "nhava sheva", "mundra", "chittagong", "chattogram", "busan", "hong kong", "kaohsiung", "port klang",
    "tanjung pelepas", "piraeus", "valencia", "algeciras", "durban", "santos", "vancouver", "oakland", "houston", "charleston", "baltimore", "haifa", "ashdod", "odesa", "odessa",
    "southampton", "le havre", "gdansk", "karachi", "chennai", "mumbai", "kolkata", "dubai", "jeddah", "port said", "mombasa", "lagos", "manila", "ho chi minh", "haiphong",
}
AIRPORT_PLACES = {
    "hong kong", "memphis", "anchorage", "louisville", "shanghai", "pudong", "incheon", "seoul", "dubai", "doha", "frankfurt", "liege", "leipzig", "luxembourg", "amsterdam",
    "schiphol", "heathrow", "london", "paris", "chicago", "miami", "los angeles", "new york", "singapore", "changi", "taipei", "taoyuan", "tokyo", "narita", "delhi", "mumbai",
    "bengaluru", "bangalore", "chennai", "hyderabad", "istanbul", "cologne", "east midlands", "brussels", "zaragoza", "maastricht", "cincinnati", "tel aviv", "bahrain", "sharjah",
    "abu dhabi", "addis ababa", "nairobi", "johannesburg", "guangzhou", "shenzhen", "zhengzhou", "ezhou", "kuala lumpur", "bangkok", "hanoi", "ho chi minh", "dhaka", "colombo",
    "karachi", "riyadh", "jeddah", "toronto", "vancouver", "atlanta", "dallas", "munich", "milan", "madrid", "vienna", "zurich", "budapest", "copenhagen", "oslo", "helsinki",
    "sydney", "melbourne", "sao paulo", "bogota", "mexico city", "kolkata", "ahmedabad",
}
AIRLINES = {
    "cargolux": "Cargolux", "lufthansa cargo": "Lufthansa Cargo", "lufthansa": "Lufthansa Cargo", "emirates skycargo": "Emirates SkyCargo", "emirates": "Emirates SkyCargo", "qatar airways cargo": "Qatar Airways Cargo",
    "qatar airways": "Qatar Airways Cargo", "fedex": "FedEx", "atlas air": "Atlas Air", "kalitta": "Kalitta Air", "cathay pacific": "Cathay Cargo", "cathay cargo": "Cathay Cargo",
    "cathay": "Cathay Cargo", "korean air": "Korean Air", "singapore airlines": "Singapore Airlines", "sia cargo": "Singapore Airlines", "turkish cargo": "Turkish Cargo",
    "turkish airlines": "Turkish Cargo", "etihad cargo": "Etihad Cargo", "etihad": "Etihad Cargo", "air france-klm": "Air France-KLM", "air france klm": "Air France-KLM",
    "afklmp": "Air France-KLM", "iag cargo": "IAG Cargo", "china airlines": "China Airlines", "eva air": "EVA Air", "sf airlines": "SF Airlines", "air china cargo": "Air China Cargo",
    "china southern": "China Southern", "china eastern": "China Eastern", "ethiopian": "Ethiopian", "saudia cargo": "Saudia Cargo", "silk way": "Silk Way", "airbridgecargo": "AirBridgeCargo",
    "volga-dnepr": "Volga-Dnepr", "asl airlines": "ASL Airlines", "western global": "Western Global", "amazon air": "Amazon Air", "air india": "Air India", "indigo": "IndiGo",
    "spicejet": "SpiceJet", "spicexpress": "SpiceJet", "american airlines": "American Airlines", "delta cargo": "Delta", "united cargo": "United", "latam cargo": "LATAM Cargo",
    "avianca cargo": "Avianca Cargo", "challenge group": "Challenge Group", "magma aviation": "Magma Aviation", "nippon cargo": "Nippon Cargo Airlines", "polar air": "Polar Air Cargo",
    "cargojet": "Cargojet", "air canada cargo": "Air Canada Cargo", "air canada": "Air Canada Cargo", "finnair cargo": "Finnair Cargo", "virgin atlantic cargo": "Virgin Atlantic Cargo",
    "swiss worldcargo": "Swiss WorldCargo", "martinair": "Martinair", "aerologic": "AeroLogic", "european air transport": "DHL",
}
AIRLINE_ACRONYMS = {"UPS": "UPS", "DHL": "DHL", "ANA": "ANA", "JAL": "JAL", "IAG": "IAG Cargo", "NCA": "Nippon Cargo Airlines", "ABC": "AirBridgeCargo", "KLM": "Air France-KLM"}
CARRIERS = {
    "maersk": "Maersk", "cma cgm": "CMA CGM", "hapag-lloyd": "Hapag-Lloyd", "hapag lloyd": "Hapag-Lloyd", "cosco": "COSCO", "evergreen": "Evergreen",
    "ocean network express": "ONE", "yang ming": "Yang Ming", "wan hai": "Wan Hai", "mediterranean shipping": "MSC", "oocl": "OOCL",
}
CARRIER_ACRONYMS = {"MSC": "MSC", "HMM": "HMM", "ZIM": "ZIM", "ONE": "ONE", "Zim": "ZIM"}

_AIR_ROLE = re.compile(r"\b(airports?|air ?cargo|air ?freight|airfreight|flights?|freighters?|airlines?|hub|aviation|aircraft)\b")
_SEA_ROLE = re.compile(r"\b(ports?|terminals?|harbou?rs?|docks?|ships?|vessels?|boxships?|tankers?|container(s|ship)?|berths?|shipping)\b")


def _find(names, low):
    """Longest names first, whole words only; a shorter name inside an already matched longer one is skipped."""
    found, taken = [], []
    for n in sorted(names, key=len, reverse=True):
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", low):
            if not any(a <= m.start() < b for a, b in taken): found.append(n); taken.append((m.start(), m.end())); break
    return found


def _acronyms(table, original):
    return [v for k, v in table.items() if re.search(r"(?<![A-Za-z0-9])" + re.escape(k) + r"(?![A-Za-z0-9])", original)]


def extract(clean_title, default_mode=None):
    """Entities of one headline. Lists are sorted and may be empty. A place that can be a port or an airport is
    assigned by the words of the headline; if those do not decide, by the source's default mode; otherwise it is dropped."""
    low = clean_title.lower()
    chokepoints = sorted({CHOKEPOINTS[n] for n in _find(CHOKEPOINTS, low)})
    countries = sorted({COUNTRIES[n][0] for n in _find(COUNTRIES, low)} | {c for c, _ in _acronyms(COUNTRY_ACRONYMS, clean_title)})
    regions = sorted({REGIONS[n] for n in _find(REGIONS, low)} | set(_acronyms(REGION_ACRONYMS, clean_title)))
    air, sea = bool(_AIR_ROLE.search(low)), bool(_SEA_ROLE.search(low))
    role = "AIR" if air and not sea else "SEA" if sea and not air else default_mode if not (air and sea) else None
    places = _find(PORT_PLACES | AIRPORT_PLACES, low)
    airports = sorted({p for p in places if p in AIRPORT_PLACES and (role == "AIR" or re.search(re.escape(p) + r"('s)? (international )?airport", low))})
    ports = sorted({p for p in places if p in PORT_PLACES and p not in airports and (role == "SEA" or re.search(r"port of " + re.escape(p) + r"|" + re.escape(p) + r"('s)? port", low))})
    airlines = sorted({AIRLINES[n] for n in _find(AIRLINES, low)} | set(_acronyms(AIRLINE_ACRONYMS, clean_title)))
    carriers = sorted({CARRIERS[n] for n in _find(CARRIERS, low)} | set(_acronyms(CARRIER_ACRONYMS, clean_title)))
    scope = "FACILITY" if (airports or ports) else "SEA_AREA" if chokepoints else "COUNTRY" if countries else "REGION" if regions else "UNKNOWN"
    return {"geographic_scope": scope, "countries": countries, "regions": sorted(set(regions) | set(chokepoints)), "airports": airports, "ports": ports,
            "airlines": airlines, "carriers": carriers, "chokepoints": chokepoints}
