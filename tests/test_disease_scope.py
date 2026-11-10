from backend.app.services.disease_scope import detect_disease_scope, is_kb_uncovered


def test_malt_maps_to_mzl_on_nccn():
    scope = detect_disease_scope("A 60-year-old with MALT lymphoma of the stomach", source="nccn")
    assert scope.key == "mzl"
    assert scope.kb_covered is True


def test_cll_uncovered_on_nccn():
    scope = detect_disease_scope("chronic lymphocytic leukemia first-line therapy", source="nccn")
    assert scope.key == "cll"
    assert is_kb_uncovered(scope)


def test_wm_uncovered_on_nccn():
    scope = detect_disease_scope("Waldenstrom macroglobulinemia IgM", source="nccn")
    assert scope.key == "wm"
    assert is_kb_uncovered(scope)


def test_cll_covered_on_csco():
    scope = detect_disease_scope("慢性淋巴细胞白血病一线治疗", source="csco")
    assert scope.key == "cll"
    assert not is_kb_uncovered(scope)


def test_dlbcl_still_maps():
    scope = detect_disease_scope("初诊 DLBCL 一线 R-CHOP", source="nccn")
    assert scope.key == "dlbcl"


def test_non_hodgkin_is_not_hl():
    scope = detect_disease_scope(
        "A woman with non-Hodgkin lymphoma develops vincristine neuropathy.",
        source="nccn",
    )
    assert scope.key != "hl"
