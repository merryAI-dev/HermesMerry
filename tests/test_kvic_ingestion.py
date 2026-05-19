from merry_runtime.ingestion.kvic import (
    build_kvic_investor_profiles,
    parse_kvic_fund_types,
    parse_kvic_funds,
)


def test_normalizes_fund_types_and_funds_from_kvic_payloads() -> None:
    fund_types = parse_kvic_fund_types(
        {"result": [{"fundCode": "11", "fundName": "한국모태펀드"}]},
        collected_at="2026-05-19T16:00:00+09:00",
    )
    funds = parse_kvic_funds(
        {
            "result_11": [
                {
                    "year": "2023년",
                    "fd": "소셜임팩트",
                    "mng": "디쓰리쥬빌리파트너스",
                    "asn": "디쓰리 임팩트 벤처투자조합 제2호",
                    "exp": "2027-08-08",
                    "amt": "30850",
                    "ca": "21000",
                }
            ],
            "code": "",
        },
        collected_at="2026-05-19T16:00:00+09:00",
        reference_date="2026-05-19",
    )

    assert fund_types == [
        {
            "fund_code": "11",
            "fund_name": "한국모태펀드",
            "source_url": "https://www.kvic.or.kr/api/businessType",
            "collected_at": "2026-05-19T16:00:00+09:00",
        }
    ]
    assert funds[0]["fund_type_code"] == "11"
    assert funds[0]["fund_year"] == 2023
    assert funds[0]["field_name"] == "소셜임팩트"
    assert funds[0]["manager_name"] == "디쓰리쥬빌리파트너스"
    assert funds[0]["association_name"] == "디쓰리 임팩트 벤처투자조합 제2호"
    assert funds[0]["expires_at"] == "2027-08-08"
    assert funds[0]["amount_raw"] == "30850"
    assert funds[0]["commitment_raw"] == "21000"
    assert funds[0]["amount_eok"] == 308.5
    assert funds[0]["commitment_eok"] == 210.0
    assert funds[0]["is_active"] is True
    assert '"mng": "디쓰리쥬빌리파트너스"' in str(funds[0]["raw_json"])


def test_builds_investor_profiles_from_full_fund_snapshot() -> None:
    funds = parse_kvic_funds(
        {
            "result_11": [
                {
                    "year": "2021년",
                    "fd": "미래환경산업",
                    "mng": "디쓰리쥬빌리파트너스",
                    "asn": "디쓰리 미래환경 ECO 벤처투자조합",
                    "exp": "2029-08-25",
                    "amt": "28500",
                    "ca": "15000",
                },
                {
                    "year": "2018년",
                    "fd": "소셜임팩트",
                    "mng": "디쓰리쥬빌리파트너스",
                    "asn": "D3 임팩트 벤처투자조합 제1호",
                    "exp": "2026-08-16",
                    "amt": "15000",
                    "ca": "12000",
                },
                {
                    "year": "2015년",
                    "fd": "문화산업",
                    "mng": "다른투자",
                    "asn": "만기펀드",
                    "exp": "2020-01-01",
                    "amt": "1000",
                    "ca": "500",
                },
            ]
        },
        collected_at="2026-05-19T16:00:00+09:00",
        reference_date="2026-05-19",
    )

    profiles = build_kvic_investor_profiles(funds, collected_at="2026-05-19T16:00:00+09:00")

    d3_profile = next(profile for profile in profiles if profile["manager_name"] == "디쓰리쥬빌리파트너스")
    assert d3_profile["manager_id"].startswith("kvic_mgr_")
    assert d3_profile["total_fund_count"] == 2
    assert d3_profile["active_fund_count"] == 2
    assert d3_profile["active_amount_eok"] == 435.0
    assert d3_profile["active_commitment_eok"] == 270.0
    assert d3_profile["fund_fields"] == ["미래환경산업", "소셜임팩트"]
    assert d3_profile["representative_funds"] == ["디쓰리 미래환경 ECO 벤처투자조합", "D3 임팩트 벤처투자조합 제1호"]
    assert d3_profile["profile_tags"] == ["climate_environment", "impact"]
    assert d3_profile["next_expiry_at"] == "2026-08-16"
