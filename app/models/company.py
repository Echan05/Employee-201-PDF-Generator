from pydantic import BaseModel, field_validator

class CompanyRecord(BaseModel):
    company: str | None = None
    company_name_con_x: str | None = None
    company_id_logo: str | None = None
    company_address_x: str | None = None
    signatory: str | None = None
    signatory_esig: str | None = None
    header: str | None = None

    @field_validator(
        "company", "company_name_con_x", "company_id_logo",
        "company_address_x", "signatory", "signatory_esig", "header",
        mode="before",
    )
    @classmethod
    def normalize_blank(cls, v):
        if v == "" or v is None:
            return None
        return v

    @field_validator("company_id_logo", mode="after")
    @classmethod
    def fix_double_colon(cls, v):
        # Live data bug: "https::\/\/..." instead of "https:\/\/..."
        if v is None:
            return v
        normalized = v.replace("https::", "https:").replace("http::", "http:")
        # API payload contains escaped slashes (e.g. "https:\/\/host\/path").
        return normalized.replace("\\/", "/")