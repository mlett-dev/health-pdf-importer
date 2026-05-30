from health_importer.workflow.validation import doctor_patient_name_too_similar


def test_doctor_patient_not_similar_when_distinct() -> None:
    assert doctor_patient_name_too_similar("Dr. Testarzt Patient", "Anna") is False


def test_doctor_patient_similar_when_doctor_contains_patient_first_name() -> None:
    assert doctor_patient_name_too_similar("Max", "Max") is True
    assert doctor_patient_name_too_similar("Dr. Max", "Max") is True


def test_doctor_patient_similar_with_minor_variation() -> None:
    assert doctor_patient_name_too_similar("Maximilian", "Maximilian Test") is True


def test_doctor_patient_handles_missing_values() -> None:
    assert doctor_patient_name_too_similar(None, "Max") is False
    assert doctor_patient_name_too_similar("Dr. Testarzt", None) is False
    assert doctor_patient_name_too_similar("", "Max") is False
