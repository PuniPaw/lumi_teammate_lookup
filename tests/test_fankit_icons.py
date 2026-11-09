"""팬키트 폴더를 API 캐릭터 코드에 맞추기 (폴더 번호가 코드와 다른 경우가 있음)."""

from lumi.debug.fankit_icons import match_folders

API = {3: "Fiora", 7: "Hyunwoo", 17: "Adriana", 18: "Shoichi", 10: "LiDailin", 80: "Istvan"}


def test_folders_are_matched_by_name_not_number():
    titles = ["003. Hyunwoo", "005. Fiora", "016. Adriana", "017. Shoichi"]
    matched, unmatched = match_folders(titles, API)
    assert matched == {"003. Hyunwoo": 7, "005. Fiora": 3, "016. Adriana": 17, "017. Shoichi": 18}
    assert unmatched == []


def test_accents_and_spaces_are_ignored_and_npcs_left_out():
    matched, unmatched = match_folders(["080. István", "010. Li Dailin", "9999. Dr. Wickeline"], API)
    assert matched == {"080. István": 80, "010. Li Dailin": 10}
    assert unmatched == ["9999. Dr. Wickeline"]
