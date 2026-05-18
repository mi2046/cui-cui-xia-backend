"""Test DeepSeek AI reminder generation"""
import asyncio
import sys
import os
sys.path.insert(0, '.')

# Fix Windows encoding
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.platform == 'win32':
    import subprocess
    subprocess.run(['chcp', '65001'], shell=True)

from services.ai_service import generate_reminder_messages


async def test():
    print("Testing AI reminder message generation...\n")

    result = await generate_reminder_messages(
        client_name="Zhang San",
        amount=5000,
        overdue_days=7,
        client_type="old",
        payment_habit="normal",
        company="Some Tech Company",
        project_title="Website Design",
    )

    print("=" * 50)
    print("AI Generated Reminder Messages")
    print("=" * 50)

    print(f"\n[WeChat Friendly]:\n{result['wechat_friendly']}")
    print(f"\n[WeChat Formal]:\n{result['wechat_formal']}")
    print(f"\n[Email]:\n{result['email']}")
    print(f"\n[Firm/Last Resort]:\n{result['firm']}")
    print(f"\n[Tip]: {result['tip']}")
    print(f"[Suggested Tone]: {result['suggested_tone']}")

    print("\n" + "=" * 50)
    print("SUCCESS: AI reminder generation test passed!")


if __name__ == "__main__":
    asyncio.run(test())
