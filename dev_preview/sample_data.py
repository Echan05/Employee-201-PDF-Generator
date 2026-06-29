"""
Sample Employee201Data for template development.

Modeled on CADORNA's real primary record (sparse - no parents/education/etc.)
PLUS synthetic secondary data so we can visually verify every template
section renders correctly, including multi-row dynamic sections.

This is for template development ONLY - never used in production.
"""
from app.models.aggregated import Employee201Data, SectionResult
from app.models.education import EducationRecord
from app.models.employment import EmploymentHistoryRecord
from app.models.minor import MinorRecord
from app.models.parent import ParentRecord
from app.models.primary import PrimaryEmployeeRecord
from app.models.training import TrainingRecord


def build_sample_data() -> Employee201Data:
    primary = PrimaryEmployeeRecord(
        rm_tran_no=53383,
        erms_id=23376492,
        rm_lastname="CADORNA",
        rm_first_name="LEONIDEZ",
        rm_middle_name="AGUILAR",
        rm_gender="MALE",
        rm_civiil_status="SINGLE",
        rm_religion="ROMAN CATHOLIC",
        rm_height="5'7\"",
        rm_weight="160",
        rm_sss_no="0423740808",
        rm_pagibig_no="121108917938",
        rm_phhealth="080256482952",
        rm_incase_contact="JAMA AGUILAR",
        rm_incase_add="SA",
        rm_incace_contactno="09950498287",
        contract_sdate="2024-06-10",
        cur_street="MALINIS COMPOUND",
        cur_subd="BANCAL",
        cur_town="CARMONA",
        cur_prov="CAVITE",
        cur_zip=4116,
        rm_contact_no="09569061903",
    )

    parents = [
        ParentRecord(fam_pooling=53383, fam_rela="FATHER", fam_name="FRANCISCO CADORNA", fam_age="59", fam_ocu="FARMER"),
        ParentRecord(fam_pooling=53383, fam_rela="MOTHER", fam_name="JINKY CADORNA", fam_age="55", fam_ocu="HOUSEWIFE"),
        ParentRecord(fam_pooling=53383, fam_rela="SIBLINGS", fam_name="MARICEL CADORNA", fam_age="28", fam_ocu="TEACHER"),
        ParentRecord(fam_pooling=53383, fam_rela="SIBLINGS", fam_name="JOSE CADORNA", fam_age="22", fam_ocu="STUDENT"),
        ParentRecord(fam_pooling=53383, fam_rela="SPOUSE", fam_name="ANALYN CADORNA", fam_age="30", fam_ocu="NURSE"),
        ParentRecord(fam_pooling=53383, fam_rela="CHILDREN", fam_name="MIGUEL CADORNA", fam_age="5", fam_ocu="NONE"),
    ]

    education = [
        EducationRecord(edu_pool_id=53383, edu_type="A.  HIGH SCHOOL", edu_school="COMMONWEALTH HIGH SCHOOL", edu_course=None, edu_year="2013-2015"),
        EducationRecord(edu_pool_id=53383, edu_type="A.  HIGH SCHOOL", edu_school="BEST LINK COLLEGE OF THE PHILIPPINES (SHS)", edu_course=None, edu_year="2015-2017"),
        EducationRecord(edu_pool_id=53383, edu_type="B. COLLEGE", edu_school="ASIAN INSTITUTE OF SCIENCE AND TECH", edu_course="ACCOUNTANCY", edu_year="UNDERGRADUATE"),
    ]

    employment = [
        EmploymentHistoryRecord(history_pooling=53383, history_company="ASIA PACIFIC AND COSMETIC PRODUCT", history_position="PROMODISER", history_sdate="2023-02-22", history_edate="2023-05-10"),
        EmploymentHistoryRecord(history_pooling=53383, history_company="GUARDHOUSE SECURITY AGENCY", history_position="SECURITY GUARD", history_sdate="2023-09-16", history_edate="2023-12-21"),
    ]

    training = [
        TrainingRecord(training_pooling_no=53383, traning_school="COUGAR SEC AGENCY", training_course="ENHANCEMENT TRAINING PROGRAM", training_sdate="2025-08-14", training_edate="2025-08-16"),
        TrainingRecord(training_pooling_no=53383, traning_school="COUGAR SEC AGENCY", training_course="REFRESHER TRAINING PROGRAM", training_sdate="2021-08-18", training_edate="2021-08-22"),
    ]

    minors: list[MinorRecord] = []

    return Employee201Data(
        primary=primary,
        parents=SectionResult(data=parents, status="ok"),
        education=SectionResult(data=education, status="ok"),
        employment=SectionResult(data=employment, status="ok"),
        training=SectionResult(data=training, status="ok"),
        minors=SectionResult(data=minors, status="ok"),
    )