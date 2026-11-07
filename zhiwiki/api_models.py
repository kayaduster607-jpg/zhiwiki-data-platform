"""HTTP 边界模型；业务层仍独立验证关键状态。"""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DocumentInput(RequestModel):
    title: str = Field(min_length=1, max_length=200)
    source_key: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=500000)


class CleaningInput(RequestModel):
    document_id: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=1, strict=True)


class DataQualityInput(RequestModel):
    # 第一版限定单篇，避免无界读取与长时间阻塞。
    document_ids: List[str] = Field(min_length=1, max_length=1)

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, values):
        if any(not value.strip() or len(value) > 100 for value in values):
            raise ValueError("文档 ID 不能为空或超过 100 字符")
        return values


class QueryInput(RequestModel):
    question: str = Field(min_length=1, max_length=4000)
    strategy: Literal["baseline", "agentic"] = "agentic"


class WikiInput(RequestModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=200)
    document_ids: List[str] = Field(min_length=1, max_length=12)


class WikiClaimInput(RequestModel):
    text: str = Field(min_length=1, max_length=10000)
    evidence_ids: List[str] = Field(min_length=1, max_length=50)


class WikiRevisionInput(RequestModel):
    expected_version: int = Field(ge=1, strict=True)
    title: str = Field(min_length=1, max_length=200)
    claims: List[WikiClaimInput] = Field(min_length=1, max_length=100)
    links: Optional[List[str]] = Field(default=None, max_length=100)
    revision_note: Optional[str] = Field(default=None, max_length=1000)


class ChunkPreviewInput(RequestModel):
    # 预览保留首尾空白，返回的 offset 才能直接对应用户输入原文。
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    text: str = Field(min_length=1, max_length=20000)
    size: int = Field(default=900, ge=200, le=2000, strict=True)
    overlap: int = Field(default=120, ge=0, le=500, strict=True)
    strategy: Literal["fixed", "structure"] = "fixed"

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("预览正文不能为空或包含 NUL 字符")
        return value

    @model_validator(mode="after")
    def check_overlap(self):
        if self.overlap > self.size / 2:
            raise ValueError("overlap 不能超过 size 的一半")
        return self
