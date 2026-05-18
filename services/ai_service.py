"""
services/ai_service.py - DeepSeek AI 话术生成服务
核心功能：根据客户信息 + 逾期情况，生成3种语气的催款话术
"""
import json
from openai import AsyncOpenAI
from typing import Optional
from config import settings


# ==================== DeepSeek 客户端 ====================

_client: Optional[AsyncOpenAI] = None


def get_deepseek_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY 未设置，请在 .env 中配置")
        _client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
        )
    return _client


# ==================== Prompt 模板 ====================

REMINDER_PROMPT_TEMPLATE = """
你是专为**中国自由职业者**设计的催款话术助手，帮助用户优雅地拿回应收账款。

【催款核心原则】
1. **礼貌但坚定** — 既不冒犯客户，又要推动付款
2. **给台阶下** — 假设客户是忙忘记了，不是故意拖欠
3. **明确但不施压** — 说清楚金额和时间，但不威胁
4. **维护长期关系** — 即使强硬版也要保持专业，不能人身攻击

【输入信息】
- 客户名称：{client_name}
- 客户公司：{company}
- 客户类型：{client_type}（new=新客户, old=老客户, vip=大客户/重点客户）
- 付款习惯：{payment_habit}（punctual=每次准时, normal=偶尔逾期, often_late=经常拖欠）
- 欠款金额：{amount}元
- 逾期天数：{overdue_days}天
- 发送渠道：{channel}（wechat=微信, email=邮件）
- 项目描述：{project_title}

【语气调整规则】
根据逾期天数自动调整语气优先级：
- 逾期 ≤ 7天：主要用友好版，语气轻松自然
- 逾期 8-30天：友好+正式版组合，提醒紧迫性
- 逾期 > 30天：正式+强硬版组合，说明后果

根据客户类型微调：
- vip客户：语气更委婉，给足面子，多用"方便的话""如果方便的话"等软化词
- new客户：语气友好，建立信任关系
- 老赖型客户：适当提高正式程度

【输出要求】
请生成4种话术（JSON格式）：

1. **wechat_friendly**（微信友好版，约50字）
   - 像朋友聊天，轻松自然
   - 适合新客户或逾期<7天
   - 可加emoji表情增加亲切感

2. **wechat_formal**（微信正式版，约80字）
   - 商务语气，明确提及合同/约定
   - 适合老客户或逾期8-30天
   - 说明时间节点，如"本周五前"

3. **email**（邮件版，约120字）
   - 正式商务邮件格式
   - 必须包含：称呼、项目名称、金额、逾期天数、付款截止时间
   - 语气专业严谨，但不威胁

4. **firm**（最后通牒版，约60字）
   - 严肃但不人身攻击
   - 必须包含后果说明（如"暂停后续服务""保留法律追责权利"）
   - 仅在逾期>30天或老赖型客户使用
   - 注意：即使是最后通牒，也要保持法律允许范围内的表达

【JSON输出格式】
```json
{{
  "wechat_friendly": "...",
  "wechat_formal": "...",
  "email": "...",
  "firm": "...",
  "tip": "这条催款建议：使用XX版本，因为...",
  "suggested_tone": "friendly"
}}
```

请严格按JSON格式输出，不要有其他文字。
"""


# ==================== 服务函数 ====================

async def generate_reminder_messages(
    client_name: str,
    amount: int,
    overdue_days: int,
    client_type: str = "old",
    payment_habit: str = "normal",
    company: Optional[str] = None,
    channel: str = "wechat",
    project_title: str = "",
) -> dict:
    """
    调用 DeepSeek API 生成催款话术

    Args:
        client_name: 客户名称
        amount: 欠款金额（元）
        overdue_days: 逾期天数
        client_type: 客户类型 (new/old/vip)
        payment_habit: 付款习惯 (punctual/normal/often_late)
        company: 公司名称
        channel: 发送渠道
        project_title: 项目描述

    Returns:
        dict: 包含4种话术和建议的字典
    """
    client = get_deepseek_client()

    # 构建 Prompt
    prompt = REMINDER_PROMPT_TEMPLATE.format(
        client_name=client_name,
        company=company or "未提供",
        client_type=client_type,
        payment_habit=payment_habit,
        amount=amount,
        overdue_days=overdue_days,
        channel=channel,
        project_title=project_title or "未提供",
    )

    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        max_tokens=2048,
        temperature=0.7,
    )

    # 解析 JSON 响应
    raw_text = response.choices[0].message.content.strip()

    # 尝试提取JSON（处理可能的markdown代码块）
    json_str = raw_text
    if "```json" in raw_text:
        start = raw_text.find("```json") + 7
        end = raw_text.find("```", start)
        json_str = raw_text[start:end].strip()
    elif "```" in raw_text:
        start = raw_text.find("```") + 3
        end = raw_text.find("```", start)
        json_str = raw_text[start:end].strip()

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        # 如果JSON解析失败，返回默认话术
        result = {
            "wechat_friendly": f"亲爱的{client_name}，您好！上次项目的尾款{amount}元方便这周安排一下吗？😊",
            "wechat_formal": f"{client_name}您好，根据合同约定，该笔{amount}元款项已逾期{overdue_days}天，请尽快安排付款。",
            "email": f"尊敬的用户您好！您有一笔{amount}元的项目款项已逾期{overdue_days}天，请尽快处理，以免影响后续合作。",
            "firm": f"此笔{amount}元款项已逾期{overdue_days}天，如本周未收到付款，我们将暂停后续服务，并保留法律追责权利。",
            "tip": "建议使用友好版催款语气，新客户优先建立信任关系",
            "suggested_tone": "friendly",
        }

    return result


async def get_reminder_suggestion(
    client_type: str,
    payment_habit: str,
    overdue_days: int,
) -> str:
    """根据客户情况给出催款建议（轻量版，不需要调用API）"""
    if overdue_days <= 3:
        return "刚逾期3天内，建议先用友好版提醒，客户可能只是忙忘了。"

    if overdue_days <= 7:
        if client_type == "vip":
            return "VIP客户刚逾期，建议用友好版，给予充分尊重。"
        return "逾期一周内，友好版催一次，如果没反应再用正式版。"

    if overdue_days <= 30:
        if payment_habit == "often_late":
            return "该客户经常拖欠，建议直接用正式版，明确付款期限。"
        return "逾期超过一周，可以用正式版，语气严谨但不失礼貌。"

    if payment_habit == "often_late" or overdue_days > 60:
        return "逾期严重且客户有老赖历史，建议用强硬版，说明后果，并考虑法律途径。"

    return "逾期较长时间，建议用正式+强硬组合版，给出明确付款期限。"
