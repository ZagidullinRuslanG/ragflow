#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import logging
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase


class Answer2Param(ComponentParamBase):
    """
    Define the Answer2 component parameters.
    Answer2 is a human-bot interaction component that also allows specifying
    a knowledge base whose parser config is used for parsing uploaded documents.
    """
    def __init__(self):
        super().__init__()
        self.kb_ids = []
        self.outputs = {
            "content": {
                "type": "str"
            }
        }

    def check(self):
        return True


class Answer2(ComponentBase):
    component_name = "Answer2"

    def get_input_elements(self) -> dict[str, Any]:
        if self._param.content:
            return self.get_input_elements_from_text("".join(self._param.content))
        return {}

    def _invoke(self, **kwargs):
        content = ""
        for k, v in self.get_input().items():
            if isinstance(v, str):
                content += v
        self.set_output("content", content)

    async def _invoke_async(self, **kwargs):
        self._invoke(**kwargs)

    def thoughts(self) -> str:
        return ""

    def get_kb_ids(self) -> list:
        return self._param.kb_ids or []
