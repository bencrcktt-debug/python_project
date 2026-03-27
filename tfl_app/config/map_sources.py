from __future__ import annotations

TEA_ARCGIS_WEBAPP_URL = "https://tea-texas.maps.arcgis.com/apps/webappviewer/index.html?id=51f0c8fa684c4d399d8d182e6edd5d97"
TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL = "https://services2.arcgis.com/5MVN2jsqIrNZD4tP/arcgis/rest/services/Map/FeatureServer/0"
TEA_ARCGIS_COUNTY_LAYER_URL = "https://services2.arcgis.com/5MVN2jsqIrNZD4tP/arcgis/rest/services/Counties2019/FeatureServer/0"
CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/25"
ARCGIS_GEOCODER_URL = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
TCEQ_WATER_DISTRICTS_LAYER_URL = "https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/TCEQ_Water_Districts/FeatureServer/0"
TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL = "https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/TCEQ_Groundwater_Conservation_Districts/FeatureServer/0"
TEXAS_RMA_LAYER_URL = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/Texas_Regional_Mobility_Authority_Boundaries/FeatureServer/0"
TEXAS_HOUSE_DISTRICTS_LAYER_URL = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/Texas_State_House_Districts/FeatureServer/0"
TEXAS_SENATE_DISTRICTS_LAYER_URL = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/Texas_State_Senate_Districts/FeatureServer/0"
TEXAS_JUNIOR_COLLEGE_LAYER_URL = "https://services1.arcgis.com/hVMNhMnY75fwfIFy/arcgis/rest/services/JuniorCollege_ServiceAreas/FeatureServer/0"
TEXAS_NAVIGATION_DISTRICT_LAYER_URL = "https://services1.arcgis.com/YWG34dhJxrbxQWdF/arcgis/rest/services/Navigation_Districts2/FeatureServer/29"
NCTCOG_TRANSIT_PROVIDERS_LAYER_URL = "https://geospatial.nctcog.org/map/rest/services/Transportation/DFWMaps_Transit/MapServer/10"
TXDOT_SEAPORTS_LAYER_URL = "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/TxDOT_Seaports/FeatureServer/0"

MAP_BASEMAP_OPTIONS = {
    "Gray Canvas": "gray-vector",
    "Street Detail": "streets-vector",
    "Satellite": "hybrid",
}

MAP_DATA_SOURCES = [
    (
        "TEA School District Locator (web app)",
        TEA_ARCGIS_WEBAPP_URL,
        "Reference viewer used for school district context.",
    ),
    (
        "TEA School District boundaries (FeatureServer/0)",
        TEA_ARCGIS_SCHOOL_DISTRICT_LAYER_URL,
        "School district polygons and centroids.",
    ),
    (
        "TEA County boundaries (FeatureServer/0)",
        TEA_ARCGIS_COUNTY_LAYER_URL,
        "County polygons and centroids.",
    ),
    (
        "U.S. Census TIGERweb Texas Places (MapServer/25)",
        CENSUS_ARCGIS_TEXAS_CITY_LAYER_URL,
        "City/place polygons and centroids for Texas (STATE=48).",
    ),
    (
        "TCEQ Water Districts (FeatureServer/0)",
        TCEQ_WATER_DISTRICTS_LAYER_URL,
        "Municipal utility, drainage, fresh water supply, irrigation, levee improvement, municipal management, regional, river authority, soil and water control, special utility, water improvement, and water control and improvement districts.",
    ),
    (
        "TCEQ Groundwater Conservation Districts (FeatureServer/0)",
        TCEQ_GROUNDWATER_DISTRICTS_LAYER_URL,
        "Groundwater conservation district boundaries.",
    ),
    (
        "Texas Regional Mobility Authorities (FeatureServer/0)",
        TEXAS_RMA_LAYER_URL,
        "Regional mobility authority boundaries.",
    ),
    (
        "Texas Junior College Service Areas (FeatureServer/0)",
        TEXAS_JUNIOR_COLLEGE_LAYER_URL,
        "Junior/community college service-area boundaries.",
    ),
    (
        "Texas Navigation Districts (FeatureServer/29)",
        TEXAS_NAVIGATION_DISTRICT_LAYER_URL,
        "Navigation district boundaries.",
    ),
    (
        "NCTCOG Transit Providers (MapServer/10)",
        NCTCOG_TRANSIT_PROVIDERS_LAYER_URL,
        "Transit provider/service-area polygons for the North Central Texas region.",
    ),
    (
        "TxDOT Seaports (FeatureServer/0)",
        TXDOT_SEAPORTS_LAYER_URL,
        "Texas seaport locations and attributes used for port-authority matching.",
    ),
    (
        "ArcGIS World Geocoding Service",
        ARCGIS_GEOCODER_URL,
        "Address geocoding for overlap point lookup plus centroid fallback for special subdivision types without statewide boundary layers.",
    ),
]
