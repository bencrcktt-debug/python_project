from __future__ import annotations

import pandas as pd

import tfl_app.map.geo_runtime as map_geo_runtime


def test_classify_requested_entity_type_handles_core_political_subdivisions() -> None:
    assert map_geo_runtime.classify_requested_entity_type("City of Austin") == "City"
    assert map_geo_runtime.classify_requested_entity_type("Aransas County") == "County"
    assert (
        map_geo_runtime.classify_requested_entity_type("Austin Independent School District")
        == "School District"
    )
    assert map_geo_runtime.classify_requested_entity_type("Port of Corpus Christi") == "Port Authority"


def test_classify_requested_entity_type_water_authority_variants() -> None:
    assert map_geo_runtime.classify_requested_entity_type("Alliance Regional Water Authority") == "River Authority"
    assert map_geo_runtime.classify_requested_entity_type("Gulf Coast Water Authority") == "River Authority"
    assert map_geo_runtime.classify_requested_entity_type("North Texas Municipal Water District") == "River Authority"
    assert map_geo_runtime.classify_requested_entity_type("Edwards Aquifer Authority") == "River Authority"
    assert map_geo_runtime.classify_requested_entity_type("Gulf Coast Waste Disposal Authority") == "River Authority"
    assert map_geo_runtime.classify_requested_entity_type("San Antonio River Authority") == "River Authority"


def test_classify_requested_entity_type_groundwater_variants() -> None:
    assert (
        map_geo_runtime.classify_requested_entity_type("High Plains Underground Water Conservation District No. 1")
        == "Groundwater Conservation District"
    )
    assert (
        map_geo_runtime.classify_requested_entity_type("Harris-Galveston Subsidence District")
        == "Groundwater Conservation District"
    )
    assert (
        map_geo_runtime.classify_requested_entity_type("Barton Springs/Edwards Aquifer Conservation District")
        == "Groundwater Conservation District"
    )


def test_classify_requested_entity_type_flood_and_misc_water() -> None:
    assert (
        map_geo_runtime.classify_requested_entity_type("Irving Flood Control District Section I")
        == "Water Control & Improvement District"
    )
    assert map_geo_runtime.classify_requested_entity_type("Dripping Springs Water Supply Corporation") == "Water Supply Corporation"
    assert map_geo_runtime.classify_requested_entity_type("San Antonio Water System") == "Water Supply Corporation"


def test_classify_requested_entity_type_management_and_improvement_districts() -> None:
    assert (
        map_geo_runtime.classify_requested_entity_type("East End Management District")
        == "Municipal Management District"
    )
    assert (
        map_geo_runtime.classify_requested_entity_type("Westwood Magnolia Parkway Improvement District")
        == "Municipal Management District"
    )


def test_classify_requested_entity_type_tollway_as_rma() -> None:
    assert map_geo_runtime.classify_requested_entity_type("North Texas Tollway Authority") == "Regional Mobility Authority"


def test_classify_requested_entity_type_hospital_expansion() -> None:
    assert map_geo_runtime.classify_requested_entity_type("Travis County Hospital District") == "Hospital District"
    assert map_geo_runtime.classify_requested_entity_type("Decatur Hospital Authority") == "Hospital District"
    assert map_geo_runtime.classify_requested_entity_type("Harris Health System") == "Hospital District"
    assert map_geo_runtime.classify_requested_entity_type("University Medical Center El Paso") == "Hospital District"


def test_classify_requested_entity_type_electric_cooperative() -> None:
    assert map_geo_runtime.classify_requested_entity_type("Bluebonnet Electric Cooperative, Inc.") == "Electric Cooperative"
    assert map_geo_runtime.classify_requested_entity_type("Sam Houston Electric Cooperative, Inc.") == "Electric Cooperative"


def test_classify_requested_entity_type_airport() -> None:
    assert map_geo_runtime.classify_requested_entity_type("DFW International Airport") == "Airport"
    assert map_geo_runtime.classify_requested_entity_type("Dallas-Fort Worth International Airport") == "Airport"


def test_classify_requested_entity_type_university() -> None:
    assert map_geo_runtime.classify_requested_entity_type("University of Houston") == "University"
    assert map_geo_runtime.classify_requested_entity_type("Texas Tech University System") == "University"
    assert map_geo_runtime.classify_requested_entity_type("Southern Methodist University") == "University"
    assert map_geo_runtime.classify_requested_entity_type("Blinn College") == "University"
    assert map_geo_runtime.classify_requested_entity_type("Lone Star College System") == "University"
    # Should NOT classify association/foundation as university
    assert map_geo_runtime.classify_requested_entity_type("Texas Southern University Foundation") == ""
    assert map_geo_runtime.classify_requested_entity_type("Independent Colleges and Universities of Texas") == ""


def test_classify_requested_entity_type_misspellings() -> None:
    assert (
        map_geo_runtime.classify_requested_entity_type("Central Texas Groundater Conservation District")
        == "Groundwater Conservation District"
    )
    assert (
        map_geo_runtime.classify_requested_entity_type("Brush Country Groundwater Conservation Distrtict")
        == "Groundwater Conservation District"
    )
    assert (
        map_geo_runtime.classify_requested_entity_type("Lost Pines Groundwater Conversation District")
        == "Groundwater Conservation District"
    )
    assert (
        map_geo_runtime.classify_requested_entity_type("Edwards Aquifier Authority")
        == "River Authority"
    )


def test_classify_requested_entity_type_excludes_private_entities() -> None:
    # Trade association (plural "Cooperatives") — not an individual cooperative
    assert map_geo_runtime.classify_requested_entity_type("Texas Electric Cooperatives, Inc.") == ""
    assert map_geo_runtime.classify_requested_entity_type("Acadian Companies Inc.") == ""
    assert map_geo_runtime.classify_requested_entity_type("Texas Farm Bureau") == ""


def test_build_tfl_name_anchored_special_matches_prefers_local_anchor(monkeypatch) -> None:
    counties = pd.DataFrame(
        [
            {"name": "Travis", "fips": "453", "lon": -97.75, "lat": 30.28},
        ]
    )
    cities = pd.DataFrame(
        [
            {"name": "Austin", "basename": "Austin", "geoid": "4805000", "lon": -97.74, "lat": 30.27},
        ]
    )

    monkeypatch.setattr(map_geo_runtime, "fetch_tea_county_centroids", lambda: counties)
    monkeypatch.setattr(map_geo_runtime, "fetch_texas_city_centroids", lambda: cities)
    monkeypatch.setattr(
        map_geo_runtime,
        "geocode_texas_entity_arcgis",
        lambda entity_name: (_ for _ in ()).throw(AssertionError("geocode should not run for local anchor matches")),
    )

    result = map_geo_runtime.build_tfl_name_anchored_special_matches(("Travis County Appraisal District",))

    assert len(result) == 1
    row = result.iloc[0]
    assert row["subdivision_type"] == "Appraisal District"
    assert row["subdivision_name"] == "Travis County Appraisal District"
    assert row["source_name"] == "Name-anchored county centroid proxy"
    assert row["subdivision_code"] == "453"


def test_build_tfl_name_anchored_special_matches_falls_back_to_geocode(monkeypatch) -> None:
    monkeypatch.setattr(map_geo_runtime, "fetch_tea_county_centroids", lambda: pd.DataFrame())
    monkeypatch.setattr(map_geo_runtime, "fetch_texas_city_centroids", lambda: pd.DataFrame([{"name": "Austin", "basename": "Austin", "geoid": "4805000", "lon": -97.74, "lat": 30.27}]))
    monkeypatch.setattr(
        map_geo_runtime,
        "geocode_texas_entity_arcgis",
        lambda entity_name: {
            "score": 92.0,
            "postal": "78701",
            "lon": -97.7431,
            "lat": 30.2672,
        },
    )

    result = map_geo_runtime.build_tfl_name_anchored_special_matches(("Mystery Transit Authority",))

    assert len(result) == 1
    row = result.iloc[0]
    assert row["subdivision_type"] == "Transit Authority"
    assert row["subdivision_name"] == "Mystery Transit Authority"
    assert row["source_name"] == "ArcGIS geocoded entity centroid (Texas)"
    assert row["subdivision_code"] == "78701"


# ── Phase 2 tests ─────────────────────────────────────────────────────────


def test_misspelling_normalization_school_districts() -> None:
    assert map_geo_runtime.classify_requested_entity_type("Leander Independend School District") == "School District"
    assert map_geo_runtime.classify_requested_entity_type("Leander Independendent School District") == "School District"
    assert map_geo_runtime.classify_requested_entity_type("Longivew ISD") == "School District"
    assert map_geo_runtime.classify_requested_entity_type("Spring Banch Independent School District") == "School District"


def test_suffix_stripping_texas_tx() -> None:
    from tfl_app.map.geo_queries import _canonical_subdivision_text

    assert _canonical_subdivision_text("City of Dallas, Texas") == "CITY OF DALLAS"
    assert _canonical_subdivision_text("El Paso County, TX") == "EL PASO COUNTY"
    assert _canonical_subdivision_text("Aransas County, Texas") == "ARANSAS COUNTY"
    # Must NOT strip TEXAS mid-string
    assert "TEXAS" in _canonical_subdivision_text("South Texas ISD")
    assert "TEXAS" in _canonical_subdivision_text("North Texas Municipal Utility District")


def test_abbreviation_expansion_ft_to_fort() -> None:
    from tfl_app.map.geo_queries import _canonical_subdivision_text

    assert _canonical_subdivision_text("City of Ft. Worth") == "CITY OF FORT WORTH"
    assert _canonical_subdivision_text("Ft. Bend County") == "FORT BEND COUNTY"


def test_county_classifier_excludes_false_positives() -> None:
    from tfl_app.map.geo_matching import _looks_like_county_name

    assert not _looks_like_county_name("American Federation of State County and Municipal Employees")
    assert not _looks_like_county_name("County & District Clerks Association of Texas")
    assert not _looks_like_county_name("Bexar County Medical Society")
    assert not _looks_like_county_name("Brown County Legislative Affairs Committee")
    assert not _looks_like_county_name("Bexar County Deputy Sheriffs Association")
    assert not _looks_like_county_name("Cameron County Housing Finance Corporation")
    assert not _looks_like_county_name("Dallas County Hospital dba Parkland Health & Hospital System")
    # Real counties still pass
    assert _looks_like_county_name("Aransas County, Texas")
    assert _looks_like_county_name("El Paso County")
    assert _looks_like_county_name("Bexar County")


def test_city_classifier_excludes_false_positives() -> None:
    from tfl_app.map.geo_matching import _looks_like_city_name

    assert not _looks_like_city_name("Atmos City Steering Committee")
    assert not _looks_like_city_name("Bay City Chamber of Commerce")
    assert not _looks_like_city_name("City Hospital at White Rock")
    assert not _looks_like_city_name("City of Austin Employees' Retirement System")
    assert not _looks_like_city_name("City of El Paso Employee Retirement Trust")
    # Real cities still pass
    assert _looks_like_city_name("City of Beeville, Texas")
    assert _looks_like_city_name("City of Dallas")
    assert _looks_like_city_name("City of Fort Worth")


