# 首版验证记录

日期：2026-10-01。

| 验证项 | 结果 |
| --- | --- |
| Windows、Python 3.12 离线单元测试 | 14 项通过 |
| skill-creator 官方 quick_validate.py | Skill is valid |
| 旧标准编号查询 | JTG/T E61-2014 指向公告明确替代它的 JTG/T 5212-2026 |
| 未来实施日期 | 2026-10-01 查询 5410-2026 时显示尚未到 2026-11-01 实施日 |
| 首版元数据证据 | 9 条官方公告/贯彻实施通知人工核对 |
| 本机真实网络同步 | 11 个目标 TLS 连接失败；已写入错误报告，没有报告更新成功 |
| GitHub 跨平台 CI 和云端抓取 | 以仓库 Actions 实际运行结论为准 |

测试涵盖候选去重、相对链接、URL 域名与协议限制、拦截页面识别、正文指纹、未来日期、旧版关系、标签映射、首次基线、无变化、正文变化、失败保留上次成功、候选不自动晋级以及待抓取队列推进。

本机网络失败不证明官方网页不存在，也不证明云端运行必定失败。任何抓取成功也只证明本轮配置目标可访问，不是对全部标准最新有效性的保证。

复现：

```powershell
python -m unittest discover -s tests -v
python skills/road-maintenance-standards/scripts/standards.py search "JTG/T E61-2014"
python skills/road-maintenance-standards/scripts/standards.py sync
```
