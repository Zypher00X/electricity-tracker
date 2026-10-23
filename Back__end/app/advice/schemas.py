import re
from datetime import date
from typing import Literal, Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1000)
    month: str | None = Field(None, pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$')
    topic: Literal['overview', 'devices', 'budget', 'plan', 'custom'] = 'custom'
    conversation_id: UUID
    request_id: UUID

    @field_validator('month')
    @classmethod
    def valid_month(cls, value):
        if value:
            parsed = date.fromisoformat(value + '-01')
            if parsed.year < 2: raise ValueError('Month outside supported range')
        return value


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=100, pattern=r'^(?:[^0-9๐-๙]|26–27 องศาเซลเซียส)*$')
    instruction: str = Field(min_length=1, max_length=350, pattern=r'^(?:[^0-9๐-๙]|26–27 องศาเซลเซียส)*$')
    reason: str = Field(min_length=1, max_length=220, pattern=r'^(?:[^0-9๐-๙]|26–27 องศาเซลเซียส)*$')
    scenario_id: str | None = Field(None, max_length=40)


class AnswerContractError(ValueError):
    pass


Text = Annotated[str, Field(min_length=1, max_length=600, pattern=r'^(?:[^0-9๐-๙]|26–27 องศาเซลเซียส)*$')]


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    in_scope: bool
    summary: str = Field(min_length=1, max_length=600, pattern=r'^(?:[^0-9๐-๙]|26–27 องศาเซลเซียส)*$')
    actions: list[Action] = Field(max_length=3)
    assumptions: list[Text] = Field(max_length=4)
    missing_data: list[Text] = Field(max_length=4)

    def check_grounding(self, facts):
        # All numerical displays originate in Python, never in generated prose.
        prose = [self.summary] + self.assumptions + self.missing_data
        for action in self.actions:
            prose += [action.title, action.instruction, action.reason]
        if any(re.search(r'[0-9๐-๙]|https?://|<[^>]+>', text.replace('26–27 องศาเซลเซียส', '')) or len(text) > 600 for text in prose):
            raise AnswerContractError('Generated prose contains unsupported numbers or markup')
        # Explicit disclaimers are not promises. Keep checking any affirmative
        # guarantee elsewhere in the same sentence after removing only these negations.
        def claims_guarantee(text):
            text = re.sub(r'(?:ไม่(?:สามารถ|อาจ|ได้|มีการ)?|ไม่ใช่(?:การ|คำ)?|ไม่มี(?:การ|คำ)?|ยังไม่(?:สามารถ)?)(?:ให้คำ)?รับประกัน', 'ไม่มีคำมั่น', text)
            return re.search(r'ไม่ต้องกังวล.{0,30}(อากาศ|จำนวนคน)|รับประกัน.{0,20}(ประหยัด|ลดค่าไฟ)', text)
        if any(claims_guarantee(text) for text in prose):
            raise AnswerContractError('Generated prose makes an unsupported guarantee')
        allowed = {row['id'] for row in facts.get('scenarios', [])}
        if any(action.scenario_id not in allowed | {None} for action in self.actions):
            raise AnswerContractError('Unknown savings scenario')
        for action in self.actions:
            if action.scenario_id and not any(term in action.instruction for term in ('ลดเวลา', 'ลดชั่วโมง', 'ลดช่วงเวลา', 'ปิดให้เร็ว', 'เลิกใช้เร็ว')):
                # Do not attach a time-reduction saving to cleaning or sleep-mode advice.
                action.scenario_id = None
        if self.in_scope and not self.actions:
            raise AnswerContractError('In-scope answer needs actionable advice')
        if not self.in_scope and self.actions:
            raise AnswerContractError('Out-of-scope answer cannot contain actions')
        return self
