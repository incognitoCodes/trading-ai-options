"""
watchlist.py — Universe of stocks and ETFs to research daily.

All tickers here are available on MooMoo SG platform for US market trading.
Includes full S&P 500 constituents plus key ETFs.

Last updated: 2026-03-01
"""

# ---------------------------------------------------------------------------
# S&P 500 Constituents (503 tickers — some companies have multiple classes)
# ---------------------------------------------------------------------------
SP500 = [
    "A",      # Agilent Technologies
    "AAPL",   # Apple
    "ABBV",   # AbbVie
    "ABNB",   # Airbnb
    "ABT",    # Abbott Laboratories
    "ACGL",   # Arch Capital Group
    "ACN",    # Accenture
    "ADBE",   # Adobe
    "ADI",    # Analog Devices
    "ADM",    # Archer-Daniels-Midland
    "ADP",    # Automatic Data Processing
    "ADSK",   # Autodesk
    "AEE",    # Ameren
    "AEP",    # American Electric Power
    "AES",    # AES Corp
    "AFL",    # Aflac
    "AIG",    # American International Group
    "AIZ",    # Assurant
    "AJG",    # Arthur J. Gallagher
    "AKAM",   # Akamai Technologies
    "ALB",    # Albemarle
    "ALGN",   # Align Technology
    "ALL",    # Allstate
    "ALLE",   # Allegion
    "AMAT",   # Applied Materials
    "AMCR",   # Amcor
    "AMD",    # AMD
    "AME",    # AMETEK
    "AMGN",   # Amgen
    "AMP",    # Ameriprise Financial
    "AMT",    # American Tower
    "AMZN",   # Amazon
    "ANET",   # Arista Networks
    # ANSS removed — acquired by Synopsys
    "AON",    # Aon
    "AOS",    # A.O. Smith
    "APA",    # APA Corp
    "APD",    # Air Products
    "APH",    # Amphenol
    "APTV",   # Aptiv
    "ARE",    # Alexandria Real Estate
    "ATO",    # Atmos Energy
    # ATVI removed — acquired by Microsoft
    "AVB",    # AvalonBay Communities
    "AVGO",   # Broadcom
    "AVY",    # Avery Dennison
    "AWK",    # American Water Works
    "AXP",    # American Express
    "AZO",    # AutoZone
    "BA",     # Boeing
    "BAC",    # Bank of America
    "BAX",    # Baxter International
    "BBWI",   # Bath & Body Works
    "BBY",    # Best Buy
    "BDX",    # Becton Dickinson
    "BEN",    # Franklin Resources
    "BF-B",   # Brown-Forman
    "BG",     # Bunge Global
    "BIIB",   # Biogen
    "BIO",    # Bio-Rad Laboratories
    "BK",     # Bank of New York Mellon
    "BKNG",   # Booking Holdings
    "BKR",    # Baker Hughes
    "BLDR",   # Builders FirstSource
    "BLK",    # BlackRock
    "BMY",    # Bristol-Myers Squibb
    "BR",     # Broadridge Financial
    "BRK-B",  # Berkshire Hathaway
    "BRO",    # Brown & Brown
    "BSX",    # Boston Scientific
    "BWA",    # BorgWarner
    "BX",     # Blackstone
    "BXP",    # BXP (Boston Properties)
    "C",      # Citigroup
    "CAG",    # Conagra Brands
    "CAH",    # Cardinal Health
    "CARR",   # Carrier Global
    "CAT",    # Caterpillar
    "CB",     # Chubb
    "CBOE",   # Cboe Global Markets
    "CBRE",   # CBRE Group
    "CCI",    # Crown Castle
    "CCL",    # Carnival Corp
    "CDNS",   # Cadence Design Systems
    "CDW",    # CDW Corp
    "CE",     # Celanese
    "CEG",    # Constellation Energy
    "CF",     # CF Industries
    "CFG",    # Citizens Financial
    "CHD",    # Church & Dwight
    "CHRW",   # C.H. Robinson
    "CHTR",   # Charter Communications
    "CI",     # Cigna Group
    "CINF",   # Cincinnati Financial
    "CL",     # Colgate-Palmolive
    "CLX",    # Clorox
    "CMCSA",  # Comcast
    "CME",    # CME Group
    "CMG",    # Chipotle
    "CMI",    # Cummins
    "CMS",    # CMS Energy
    "CNC",    # Centene
    "CNP",    # CenterPoint Energy
    "COF",    # Capital One
    "COO",    # CooperCompanies
    "COP",    # ConocoPhillips
    "COR",    # Cencora
    "COST",   # Costco
    "CPAY",   # Corpay
    "CPB",    # Campbell Soup
    "CPRT",   # Copart
    "CPT",    # Camden Property Trust
    "CRL",    # Charles River Labs
    "CRM",    # Salesforce
    "CRWD",   # CrowdStrike
    "CSCO",   # Cisco
    "CSGP",   # CoStar Group
    "CSX",    # CSX Corp
    "CTAS",   # Cintas
    # CTLT removed — acquired by Novo Holdings
    "CTRA",   # Coterra Energy
    "CTSH",   # Cognizant
    "CTVA",   # Corteva
    "CVS",    # CVS Health
    "CVX",    # Chevron
    "CZR",    # Caesars Entertainment
    "D",      # Dominion Energy
    "DAL",    # Delta Air Lines
    "DAY",    # Dayforce
    "DD",     # DuPont
    "DE",     # Deere & Co
    "DECK",   # Deckers Outdoor
    # DFS removed — acquired by Capital One
    "DG",     # Dollar General
    "DGX",    # Quest Diagnostics
    "DHI",    # D.R. Horton
    "DHR",    # Danaher
    "DIS",    # Disney
    "DLTR",   # Dollar Tree
    "DOV",    # Dover Corp
    "DOW",    # Dow Inc
    "DPZ",    # Domino's Pizza
    "DRI",    # Darden Restaurants
    "DTE",    # DTE Energy
    "DUK",    # Duke Energy
    "DVA",    # DaVita
    "DVN",    # Devon Energy
    "DXCM",   # DexCom
    "EA",     # Electronic Arts
    "EBAY",   # eBay
    "ECL",    # Ecolab
    "ED",     # Consolidated Edison
    "EFX",    # Equifax
    "EIX",    # Edison International
    "EL",     # Estee Lauder
    "EMN",    # Eastman Chemical
    "EMR",    # Emerson Electric
    "ENPH",   # Enphase Energy
    "EOG",    # EOG Resources
    "EPAM",   # EPAM Systems
    "EQIX",   # Equinix
    "EQR",    # Equity Residential
    "EQT",    # EQT Corp
    "ERIE",   # Erie Indemnity
    "ES",     # Eversource Energy
    "ESS",    # Essex Property Trust
    "ETN",    # Eaton Corp
    "ETR",    # Entergy
    "EVRG",   # Evergy
    "EW",     # Edwards Lifesciences
    "EXC",    # Exelon
    "EXPD",   # Expeditors International
    "EXPE",   # Expedia
    "EXR",    # Extra Space Storage
    "F",      # Ford
    "FANG",   # Diamondback Energy
    "FAST",   # Fastenal
    # FBHS removed — delisted
    "FCX",    # Freeport-McMoRan
    "FDS",    # FactSet Research
    "FDX",    # FedEx
    "FE",     # FirstEnergy
    "FFIV",   # F5 Networks
    # FI removed — ticker changed (Fiserv now FISV)
    "FICO",   # Fair Isaac Corp
    "FIS",    # Fidelity National Info
    "FITB",   # Fifth Third Bancorp
    # FLT removed — renamed to CPAY (already in list)
    "FMC",    # FMC Corp
    "FOX",    # Fox Corp (Class B)
    "FOXA",   # Fox Corp (Class A)
    "FRT",    # Federal Realty
    "FSLR",   # First Solar
    "FTNT",   # Fortinet
    "FTV",    # Fortive
    "GD",     # General Dynamics
    "GDDY",   # GoDaddy
    "GE",     # GE Aerospace
    "GEHC",   # GE HealthCare
    "GEN",    # Gen Digital
    "GEV",    # GE Vernova
    "GILD",   # Gilead Sciences
    "GIS",    # General Mills
    "GL",     # Globe Life
    "GLW",    # Corning
    "GM",     # General Motors
    "GNRC",   # Generac
    "GOOG",   # Alphabet (Class C)
    "GOOGL",  # Alphabet (Class A)
    "GPC",    # Genuine Parts
    "GPN",    # Global Payments
    "GRMN",   # Garmin
    "GS",     # Goldman Sachs
    "GWW",    # W.W. Grainger
    "HAL",    # Halliburton
    "HAS",    # Hasbro
    "HBAN",   # Huntington Bancshares
    "HCA",    # HCA Healthcare
    "HD",     # Home Depot
    "HOLX",   # Hologic
    "HON",    # Honeywell
    "HPE",    # Hewlett Packard Enterprise
    "HPQ",    # HP Inc
    "HRL",    # Hormel Foods
    "HSIC",   # Henry Schein
    "HST",    # Host Hotels
    "HSY",    # Hershey
    "HUBB",   # Hubbell
    "HUM",    # Humana
    "HWM",    # Howmet Aerospace
    "IBM",    # IBM
    "ICE",    # Intercontinental Exchange
    "IDXX",   # IDEXX Laboratories
    "IEX",    # IDEX Corp
    "IFF",    # International Flavors
    "ILMN",   # Illumina
    "INCY",   # Incyte
    "INTC",   # Intel
    "INTU",   # Intuit
    "INVH",   # Invitation Homes
    "IP",     # International Paper
    # IPG removed — acquired by Omnicom
    "IQV",    # IQVIA
    "IR",     # Ingersoll Rand
    "IRM",    # Iron Mountain
    "ISRG",   # Intuitive Surgical
    "IT",     # Gartner
    "ITW",    # Illinois Tool Works
    "IVZ",    # Invesco
    "J",      # Jacobs Solutions
    "JBHT",   # J.B. Hunt Transport
    "JBL",    # Jabil
    "JCI",    # Johnson Controls
    "JKHY",   # Jack Henry & Associates
    "JNJ",    # Johnson & Johnson
    # JNPR removed — acquired by HPE
    "JPM",    # JPMorgan Chase
    # K removed — Kellanova acquired by Mars
    "KDP",    # Keurig Dr Pepper
    "KEY",    # KeyCorp
    "KEYS",   # Keysight Technologies
    "KHC",    # Kraft Heinz
    "KIM",    # Kimco Realty
    "KLAC",   # KLA Corp
    "KMB",    # Kimberly-Clark
    "KMI",    # Kinder Morgan
    "KMX",    # CarMax
    "KO",     # Coca-Cola
    "KR",     # Kroger
    "KVUE",   # Kenvue
    "L",      # Loews Corp
    "LDOS",   # Leidos
    "LEN",    # Lennar
    "LH",     # Labcorp
    "LHX",    # L3Harris Technologies
    "LIN",    # Linde
    "LKQ",    # LKQ Corp
    "LLY",    # Eli Lilly
    "LMT",    # Lockheed Martin
    "LNT",    # Alliant Energy
    "LOW",    # Lowe's
    "LRCX",   # Lam Research
    "LULU",   # Lululemon
    "LUV",    # Southwest Airlines
    "LVS",    # Las Vegas Sands
    "LW",     # Lamb Weston
    "LYB",    # LyondellBasell
    "LYV",    # Live Nation
    "MA",     # Mastercard
    "MAA",    # Mid-America Apartment
    "MAR",    # Marriott International
    "MAS",    # Masco
    "MCD",    # McDonald's
    "MCHP",   # Microchip Technology
    "MCK",    # McKesson
    "MCO",    # Moody's
    "MDLZ",   # Mondelez
    "MDT",    # Medtronic
    "MET",    # MetLife
    "META",   # Meta Platforms
    "MGM",    # MGM Resorts
    "MHK",    # Mohawk Industries
    "MKC",    # McCormick
    "MKTX",   # MarketAxess
    "MLM",    # Martin Marietta
    "MMC",    # Marsh & McLennan
    "MMM",    # 3M
    "MNST",   # Monster Beverage
    "MO",     # Altria Group
    "MOH",    # Molina Healthcare
    "MOS",    # Mosaic
    "MPC",    # Marathon Petroleum
    "MPWR",   # Monolithic Power
    "MRK",    # Merck
    "MRNA",   # Moderna
    # MRO removed — acquired by ConocoPhillips
    "MS",     # Morgan Stanley
    "MSCI",   # MSCI
    "MSFT",   # Microsoft
    "MSI",    # Motorola Solutions
    "MTB",    # M&T Bank
    "MTCH",   # Match Group
    "MTD",    # Mettler-Toledo
    "MU",     # Micron
    "NCLH",   # Norwegian Cruise Line
    "NDAQ",   # Nasdaq Inc
    "NDSN",   # Nordson
    "NEE",    # NextEra Energy
    "NEM",    # Newmont
    "NFLX",   # Netflix
    "NI",     # NiSource
    "NKE",    # Nike
    "NOC",    # Northrop Grumman
    "NOW",    # ServiceNow
    "NRG",    # NRG Energy
    "NSC",    # Norfolk Southern
    "NTAP",   # NetApp
    "NTRS",   # Northern Trust
    "NUE",    # Nucor
    "NVDA",   # NVIDIA
    "NVR",    # NVR Inc
    "NWS",    # News Corp (Class B)
    "NWSA",   # News Corp (Class A)
    "NXPI",   # NXP Semiconductors
    "O",      # Realty Income
    "ODFL",   # Old Dominion Freight
    "OKE",    # ONEOK
    "OMC",    # Omnicom
    "ON",     # ON Semiconductor
    "ORCL",   # Oracle
    "ORLY",   # O'Reilly Automotive
    "OTIS",   # Otis Worldwide
    "OXY",    # Occidental Petroleum
    "PANW",   # Palo Alto Networks
    # PARA removed — acquired by Skydance
    "PAYC",   # Paycom Software
    "PAYX",   # Paychex
    "PCAR",   # PACCAR
    "PCG",    # PG&E
    # PEAK removed — merged into DOC
    "PEG",    # Public Service Enterprise
    "PEP",    # PepsiCo
    "PFE",    # Pfizer
    "PFG",    # Principal Financial
    "PG",     # Procter & Gamble
    "PGR",    # Progressive
    "PH",     # Parker-Hannifin
    "PHM",    # PulteGroup
    "PKG",    # Packaging Corp
    "PLD",    # Prologis
    "PLTR",   # Palantir
    "PM",     # Philip Morris
    "PNC",    # PNC Financial
    "PNR",    # Pentair
    "PNW",    # Pinnacle West
    "PODD",   # Insulet
    "POOL",   # Pool Corp
    "PPG",    # PPG Industries
    "PPL",    # PPL Corp
    "PRU",    # Prudential Financial
    "PSA",    # Public Storage
    "PSX",    # Phillips 66
    "PTC",    # PTC Inc
    "PVH",    # PVH Corp
    "PWR",    # Quanta Services
    # PXD removed — acquired by Exxon
    "PYPL",   # PayPal
    "QCOM",   # Qualcomm
    "QRVO",   # Qorvo
    "RCL",    # Royal Caribbean
    "REG",    # Regency Centers
    "REGN",   # Regeneron
    "RF",     # Regions Financial
    "RHI",    # Robert Half
    "RJF",    # Raymond James
    "RL",     # Ralph Lauren
    "RMD",    # ResMed
    "ROK",    # Rockwell Automation
    "ROL",    # Rollins
    "ROP",    # Roper Technologies
    "ROST",   # Ross Stores
    "RSG",    # Republic Services
    "RTX",    # RTX Corp
    "RVTY",   # Revvity
    "SBAC",   # SBA Communications
    "SBUX",   # Starbucks
    "SCHW",   # Charles Schwab
    "SEE",    # Sealed Air
    "SHW",    # Sherwin-Williams
    "SJM",    # J.M. Smucker
    "SLB",    # Schlumberger
    "SMCI",   # Super Micro Computer
    "SNA",    # Snap-on
    "SNPS",   # Synopsys
    "SO",     # Southern Company
    "SPG",    # Simon Property Group
    "SPGI",   # S&P Global
    "SRE",    # Sempra
    "STE",    # STERIS
    "STLD",   # Steel Dynamics
    "STT",    # State Street
    "STX",    # Seagate Technology
    "STZ",    # Constellation Brands
    "SWK",    # Stanley Black & Decker
    "SWKS",   # Skyworks Solutions
    "SYF",    # Synchrony Financial
    "SYK",    # Stryker
    "SYY",    # Sysco
    "T",      # AT&T
    "TAP",    # Molson Coors
    "TDG",    # TransDigm
    "TDY",    # Teledyne Technologies
    "TECH",   # Bio-Techne
    "TEL",    # TE Connectivity
    "TER",    # Teradyne
    "TFC",    # Truist Financial
    "TFX",    # Teleflex
    "TGT",    # Target
    "TJX",    # TJX Companies
    "TMO",    # Thermo Fisher
    "TMUS",   # T-Mobile US
    "TPR",    # Tapestry
    "TRGP",   # Targa Resources
    "TRMB",   # Trimble
    "TROW",   # T. Rowe Price
    "TRV",    # Travelers
    "TSCO",   # Tractor Supply
    "TSLA",   # Tesla
    "TSN",    # Tyson Foods
    "TT",     # Trane Technologies
    "TTWO",   # Take-Two Interactive
    "TXN",    # Texas Instruments
    "TXT",    # Textron
    "TYL",    # Tyler Technologies
    "UAL",    # United Airlines
    "UBER",   # Uber
    "UDR",    # UDR Inc
    "UHS",    # Universal Health Services
    "ULTA",   # Ulta Beauty
    "UNH",    # UnitedHealth
    "UNP",    # Union Pacific
    "UPS",    # United Parcel Service
    "URI",    # United Rentals
    "USB",    # U.S. Bancorp
    "V",      # Visa
    "VICI",   # VICI Properties
    "VLO",    # Valero Energy
    "VLTO",   # Veralto
    "VMC",    # Vulcan Materials
    "VRSK",   # Verisk Analytics
    "VRSN",   # VeriSign
    "VRTX",   # Vertex Pharmaceuticals
    "VST",    # Vistra
    "VTR",    # Ventas
    "VTRS",   # Viatris
    "VZ",     # Verizon
    "WAB",    # Westinghouse Air Brake
    "WAT",    # Waters Corp
    # WBA removed — delisted
    "WBD",    # Warner Bros Discovery
    "WDC",    # Western Digital
    "WEC",    # WEC Energy
    "WELL",   # Welltower
    "WFC",    # Wells Fargo
    "WM",     # Waste Management
    "WMB",    # Williams Companies
    "WMT",    # Walmart
    "WRB",    # W.R. Berkley
    # WRK removed — acquired by Smurfit Kappa
    "WST",    # West Pharmaceutical
    "WTW",    # Willis Towers Watson
    "WY",     # Weyerhaeuser
    "WYNN",   # Wynn Resorts
    "XEL",    # Xcel Energy
    "XOM",    # Exxon Mobil
    "XYL",    # Xylem
    "YUM",    # Yum! Brands
    "ZBH",    # Zimmer Biomet
    "ZBRA",   # Zebra Technologies
    "ZION",   # Zions Bancorporation
    "ZTS",    # Zoetis
]

# --- Sector ETFs ---
SECTOR_ETFS = [
    "XLK",    # Technology
    "XLF",    # Financials
    "XLV",    # Healthcare
    "XLE",    # Energy
    "XLI",    # Industrials
    "XLY",    # Consumer Discretionary
    "XLP",    # Consumer Staples
    "XLU",    # Utilities
    "XLB",    # Materials
    "XLRE",   # Real Estate
    "XLC",    # Communication Services
]

# --- Broad Market ETFs ---
BROAD_ETFS = [
    "SPY",    # S&P 500
    "QQQ",    # Nasdaq 100
    "VOO",    # Vanguard S&P 500
    "VTI",    # Vanguard Total Market
    "IWM",    # Russell 2000 (small cap)
    "DIA",    # Dow Jones
    "VGT",    # Vanguard Info Tech
    "ARKK",   # ARK Innovation
    "SCHD",   # Schwab US Dividend
]

# --- Thematic / Leveraged ETFs ---
THEMATIC_ETFS = [
    "SOXX",   # Semiconductor ETF
    "SMH",    # VanEck Semiconductor
    "TAN",    # Solar ETF
    "LIT",    # Lithium & Battery ETF
    "BOTZ",   # Robotics & AI ETF
    "HACK",   # Cybersecurity ETF
    "GLD",    # Gold ETF
    "SLV",    # Silver ETF
    "TLT",    # 20+ Year Treasury Bond
    "HYG",    # High Yield Corporate Bond
    "XBI",    # Biotech ETF
    "KWEB",   # China Internet ETF
    "EEM",    # Emerging Markets ETF
    "EFA",    # Developed International Markets
    "VNQ",    # Real Estate ETF
    "JETS",   # Airlines ETF
    "XHB",    # Homebuilders ETF
]

# --- Leveraged / Inverse ETFs ---
LEVERAGED_ETFS = [
    "TQQQ",   # 3x Nasdaq Long
    "SQQQ",   # 3x Nasdaq Short
    "SOXL",   # 3x Semiconductor Long
    "SOXS",   # 3x Semiconductor Short
    "SPXL",   # 3x S&P 500 Long
    "SPXS",   # 3x S&P 500 Short
    "UPRO",   # 3x S&P 500 Long
    "TNA",    # 3x Russell 2000 Long
    "TZA",    # 3x Russell 2000 Short
    "LABU",   # 3x Biotech Long
    "LABD",   # 3x Biotech Short
    "NUGT",   # 2x Gold Miners Long
    "DUST",   # 2x Gold Miners Short
    "UVXY",   # 1.5x VIX Short-Term
    "SVXY",   # -0.5x VIX Short-Term (inverse)
    "TECL",   # 3x Technology Long
    "TECS",   # 3x Technology Short
    "FAS",    # 3x Financial Long
    "FAZ",    # 3x Financial Short
    "FNGU",   # 3x FANG+ Long
    "FNGD",   # 3x FANG+ Short
]

# --- Forex ETFs (accessible on MooMoo) ---
FOREX_ETFS = [
    "UUP",    # US Dollar Bullish
    "FXE",    # Euro
    "FXY",    # Japanese Yen
    "FXB",    # British Pound
    "FXA",    # Australian Dollar
]

# All ETFs combined
ALL_ETFS = BROAD_ETFS + SECTOR_ETFS + THEMATIC_ETFS + LEVERAGED_ETFS + FOREX_ETFS

# NASDAQ-100 + Top S&P 500 mega/large-caps for daily analysis
# These are the stocks a JP Morgan desk would cover daily
NASDAQ_100_PLUS = [
    # Mega-Cap Tech (Mag 7 + extended)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "ORCL", "CRM", "ADBE", "AMD", "NFLX", "CSCO", "QCOM", "INTU",
    "AMAT", "MU", "NOW", "ANET", "SNPS", "CDNS", "KLAC", "LRCX",
    "MRVL", "FTNT", "PANW", "CRWD",
    # NASDAQ-100 Large-Cap Tech
    "MELI", "PYPL", "NXPI", "ON", "ISRG", "REGN", "VRTX", "DXCM",
    "IDXX", "MNST", "ADP", "ADI", "MCHP", "TTWO", "EA", "CTAS",
    "PCAR", "ODFL", "FAST", "CPRT", "ROST",
    # High-Growth / Platform
    "UBER", "PLTR", "ARM", "DASH", "COIN", "SHOP", "SNOW", "DDOG",
    # Mega-Cap Financials
    "BRK-B", "JPM", "V", "MA", "GS", "MS", "AXP", "SPGI", "MCO",
    "BLK", "SCHW", "CME", "ICE", "COF",
    # Mega-Cap Healthcare
    "UNH", "LLY", "JNJ", "MRK", "ABBV", "TMO", "ABT", "DHR",
    "BSX", "SYK", "MDT", "AMGN",
    # Mega-Cap Consumer / Industrial
    "HD", "COST", "WMT", "PG", "KO", "PEP", "MCD", "NKE",
    "TJX", "LULU", "BKNG", "ABNB", "CMG", "SBUX",
    "CAT", "DE", "HON", "GE", "RTX", "LMT", "UNP", "ETN",
    # Energy / Power / Utilities
    "XOM", "CVX", "COP", "LIN", "NEE", "CEG", "VST",
    # Communications
    "DIS", "CMCSA", "TMUS",
]

# Quick scan = NASDAQ-100+ plus key ETFs (comprehensive daily coverage)
QUICK_SCAN = list(dict.fromkeys(
    ["SPY", "QQQ"] + NASDAQ_100_PLUS + [
        # Key ETFs
        "SOXX", "XLK", "XLF", "XLV", "XLE", "GLD", "TLT", "HYG",
        # Leveraged ETFs
        "TQQQ", "SQQQ", "SOXL", "SOXS", "SPXL", "UVXY", "FNGU", "LABU",
        # Thematic ETFs
        "SMH", "HACK", "XBI", "KWEB", "TAN", "JETS",
    ]
))

# NASDAQ-100 stocks not already in S&P 500 (high-growth names outside the S&P)
NASDAQ_EX_SP500 = [t for t in NASDAQ_100_PLUS if t not in set(SP500)]

# ---------------------------------------------------------------------------
# Russell 1000 (approximate snapshot)
# ---------------------------------------------------------------------------
# The Russell 1000 is the ~1,000 largest US companies and reconstitutes every
# June, so treat this as a maintained approximation rather than the exact live
# index. It is built as the S&P 500, plus NASDAQ-100 names outside the S&P,
# plus the curated large/mid-cap list below (mostly Russell 1000 members that
# sit outside the S&P 500). Duplicates are removed by dict.fromkeys, so overlap
# with the S&P 500 is harmless. To refresh, replace RUSSELL_1000_EXTRA with the
# current iShares Russell 1000 (IWB) holdings minus the S&P 500.
RUSSELL_1000_EXTRA = [
    # Software / internet / fintech
    "NET", "ZS", "MDB", "CFLT", "GTLB", "S", "ESTC", "TEAM",
    "HUBS", "DOCU", "ZM", "TWLO", "OKTA", "DBX", "BILL", "PCTY",
    "PAYC", "TYL", "PTC", "SSNC", "MANH", "DAY", "ASAN", "MNDY",
    "FROG", "BRZE", "AI", "APP", "TTD", "ROKU", "PINS", "SNAP",
    "SPOT", "RDDT", "DUOL", "TOST", "AFRM", "UPST", "SOFI", "NU",
    "CART", "YELP", "WIX", "PATH", "FIVN", "RNG", "APPN", "PD",
    "FSLY", "DOCN", "PSTG", "NTNX", "CVLT", "RPD", "TENB", "QLYS",
    "VRNS", "AMPL", "FLYW", "PAYO", "EEFT", "WEX", "DLO", "GDOT",
    # Semiconductors / equipment
    "SEDG", "WOLF", "LSCC", "POWI", "SITM", "ALGM", "AMKR", "QRVO",
    "SWKS", "FORM", "ACLS", "CRUS", "DIOD", "SLAB", "ONTO", "UCTT",
    "RMBS", "MTSI", "SMTC", "CRDO", "AEIS", "PLAB", "CEVA", "INDI",
    "NVTS", "VECO", "CAMT", "COHU",
    # Biotech / pharma
    "SRPT", "EXEL", "HALO", "NBIX", "ALNY", "IONS", "BMRN", "UTHR",
    "RARE", "ARWR", "ACAD", "PTCT", "FOLD", "INSM", "KRYS", "CYTK",
    "VKTX", "ROIV", "TGTX", "MDGL", "IMVT", "CPRX", "AXSM", "HRMY",
    "TWST", "PACB", "NTLA", "BEAM", "VERV", "RXRX", "TEM", "HIMS",
    "DOCS", "PGNY", "ITCI", "BPMC", "DVAX", "CRNX", "RVMD", "SMMT",
    "ARDX", "AKRO", "PCVX", "MIRM", "AGIO", "APLS", "COGT", "KYMR",
    "RCKT", "CRSP", "EDIT", "ALKS", "SUPN", "PBH", "AMPH", "CORT",
    "LNTH", "ANIP", "COLL",
    # Healthcare providers / devices
    "THC", "UHS", "CYH", "EHC", "SGRY", "OPCH", "ACHC", "USPH",
    "ENSG", "ADUS", "AMED", "CHE", "HQY", "PEN", "INSP", "GKOS",
    "SHC", "NARI", "TNDM", "TMDX", "NEOG", "MEDP", "ICLR", "RGEN",
    "BRKR", "QDEL", "NVCR", "AXNX", "ATEC", "CNMD", "IART", "MMSI",
    "OSCR", "ALHC", "PRVA",
    # Banks (regional) / financials
    "ALLY", "CG", "ARES", "OWL", "STEP", "HLNE", "TPG", "JHG",
    "IBKR", "VIRT", "TW", "SEIC", "VOYA", "CNO", "WAL", "PB",
    "CFR", "SNV", "BOKF", "PNFP", "CBSH", "WBS", "VLY", "CADE",
    "ONB", "UBSI", "FNB", "HWC", "FULT", "ASB", "WAFD", "GBCI",
    "CATY", "HOMB", "TCBI", "WTFC", "FHB", "CVBF", "PPBI", "INDB",
    "UMBF", "BANF", "FFIN", "SFBS", "AUB", "OZK", "COLB", "BKU",
    "FIBK", "WSFS", "AX", "EBC",
    # Insurance / asset managers
    "RGA", "RNR", "KNSL", "RYAN", "ORI", "AFG", "MTG", "ESNT",
    "RDN", "FNF", "FAF", "SIGI", "KMPR", "PLMR", "GSHD", "AGO",
    "LMND", "AB", "APAM", "VCTR", "WT", "VRTS",
    # Industrials / machinery / defense
    "FIX", "PRIM", "MTZ", "EME", "IESC", "GVA", "TTEK", "EXPO",
    "POWL", "NVT", "AYI", "ATKR", "AAON", "WCC", "AIT", "MSM",
    "ITT", "CR", "FLS", "GGG", "GTLS", "ENOV", "MIDD", "WTS",
    "RBC", "HLIO", "KMT", "TKR", "GTES", "HI", "HAYW", "JBT",
    "CSWI", "SPXC", "EPAC", "BWXT", "AVAV", "KTOS", "MRCY", "CW",
    "SAIC", "CACI", "AGCO", "CNH", "LNN", "ALG",
    # Transport / logistics
    "SAIA", "XPO", "ARCB", "KNX", "WERN", "SNDR", "HTLD", "MRTN",
    "RXO", "GXO", "R", "MATX", "KEX", "CAR", "HUBG", "SKYW",
    "ALGT", "JBLU", "ZIM", "STNG", "INSW", "FRO",
    # Consumer discretionary / retail
    "DECK", "ELF", "CROX", "BOOT", "ONON", "BIRK", "COLM", "YETI",
    "LEVI", "ANF", "AEO", "URBN", "DDS", "M", "JWN", "DKS",
    "FL", "FIVE", "OLLI", "BJ", "PSMT", "GO", "SFM", "CHWY",
    "W", "FND", "VVV", "MNRO", "GPI", "PAG", "LAD", "ABG",
    "CVNA", "SIG", "CWH", "FTDR", "PLNT",
    # Restaurants
    "WING", "CAVA", "SG", "BROS", "SHAK", "EAT", "BLMN", "CAKE",
    "JACK", "WEN", "PZZA", "CBRL", "PTLO", "DNUT", "YUMC",
    # Consumer staples
    "SAM", "POST", "BRBR", "FRPT", "THS", "UTZ", "CALM", "LANC",
    "JJSF", "FLO", "HAIN", "SMPL", "VITL", "CENT", "COTY", "IPAR",
    "USNA", "HELE", "ENR", "EPC", "NUS", "BGS",
    # Energy E&P / services / midstream
    "AR", "RRC", "EXE", "MTDR", "PR", "CIVI", "SM", "MGY",
    "CRGY", "CNX", "CRK", "NOG", "TALO", "VNOM", "DINO", "PARR",
    "DK", "CVI", "VTLE", "CHX", "WHD", "LBRT", "PTEN", "HP",
    "NBR", "RIG", "VAL", "TDW", "OII", "HLX", "FTI", "ET",
    "EPD", "MPLX", "PAA", "PAGP", "WES", "DTM", "ENLC", "AM",
    "SUN", "ARLP", "BTU", "AMR", "HCC", "CEIX", "UEC", "UUUU",
    # Utilities
    "OGE", "IDA", "POR", "ALE", "BKH", "NWE", "AVA", "OTTR",
    "MGEE", "NJR", "SWX", "SR", "SJW", "AWR", "CWT", "MSEX",
    "UGI", "NFG", "NWN", "CWEN",
    # Materials / metals / chemicals
    "CMC", "CLF", "ATI", "CRS", "WOR", "MLI", "SCHN", "MP",
    "CBT", "KWR", "IOSP", "SXT", "FUL", "HUN", "OLN", "ASH",
    "CC", "TROX", "KRO", "ALTM", "SCCO", "HL", "CDE", "PAAS",
    "AG", "SSRM", "BTG", "EGO", "EXP", "USLM", "SLGN", "GEF",
    "ATR", "OI", "GPK", "MATV",
    # Building products / homebuilders
    "BLD", "IBP", "AZEK", "JELD", "AWI", "NX", "GFF", "AMWD",
    "PATK", "ROCK", "CVCO", "SKY", "LGIH", "TMHC", "MTH", "TPH",
    "CCS", "GRBK", "DFH", "KBH",
    # Autos / parts
    "RIVN", "LCID", "GT", "ADNT", "DAN", "VC", "MOD", "DORM",
    "SMP", "THRM", "GNTX", "ALSN", "LCII", "WGO", "THO", "REVG",
    "HOG", "BC", "FOXF",
    # Media / telecom / communications
    "NYT", "LBRDK", "LBRDA", "FWONK", "FWONA", "LSXMK", "EDR", "CNK",
    "IMAX", "FUBO", "NXST", "TGNA", "SSP", "WMG", "TKO", "MSGS",
    "MSGE", "LUMN", "TDS", "ATUS", "CABO", "CCOI", "SHEN", "IRDM",
    "VSAT", "SATS", "GSAT", "ASTS", "COMM", "LITE", "CALX", "EXTR",
    # Travel / leisure / gaming
    "EXPE", "TRIP", "WH", "CHH", "TNL", "HGV", "VAC", "PLYA",
    "OSW", "BYD", "RRR", "BALY", "PENN", "GDEN", "MCRI", "FLUT",
    "DKNG", "RSI", "LNW", "MODG", "GOLF", "XPOF",
    # Agriculture / food producers
    "INGR", "DAR", "ANDE", "PPC", "DOLE", "CVGW", "LMNR", "SEB",
    "IPI", "SMG", "UAN", "AVD",
    # Business / IT services
    "KFY", "HSII", "ASGN", "KELYA", "TNET", "NSP", "BBSI", "CBZ",
    "EXLS", "WNS", "G", "ICFI", "HURN", "FCN", "CRAI",
    # REITs (outside the S&P 500)
    "STAG", "TRNO", "FR", "COLD", "LINE", "NSA", "EPRT", "ADC",
    "BNL", "FCPT", "PECO", "ROIC", "KRG", "AKR", "IVT", "SKT",
    "HIW", "DEI", "CUZ", "BDN", "CDP", "ESRT", "PGRE", "HPP",
    "AAT", "IRT", "NXRT", "APLE", "RLJ", "DRH", "SHO", "XHR",
    "PEB", "INN", "LTC", "SBRA", "CTRE", "NHI", "MPW", "GMRE",
    "DHC", "PCH", "RYN", "OUT", "EPR", "SVC", "HR", "CTO",
    "GNL", "NTST", "PLYM", "SAFE", "GOOD", "LAND", "FPI", "HASI",
    # Hardware / networking / electronics
    "CIEN", "NTCT", "PLXS", "BHE", "SANM", "CLS", "OSIS", "MKSI",
    "ADTN", "KN", "BDC", "VNT", "NOVT", "ITRI", "BMI",
]

# Russell 1000 = S&P 500 ∪ NASDAQ-100 (outside S&P) ∪ curated extras above.
RUSSELL_1000 = list(dict.fromkeys(SP500 + NASDAQ_EX_SP500 + RUSSELL_1000_EXTRA))

# Default watchlist = S&P 500 ∪ NASDAQ-100 + ALL ETFs (full universe)
DEFAULT_WATCHLIST = list(dict.fromkeys(SP500 + NASDAQ_EX_SP500 + ALL_ETFS))

# Extended watchlist (backward compatibility)
FULL_WATCHLIST = DEFAULT_WATCHLIST
