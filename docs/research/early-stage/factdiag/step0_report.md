# K第0步结果

状态：通过。盲审共38条，A类28条；继续门槛为至少1条A。

其中机器USER 28条、盲确认A 28条。新会话代理盲审，非人工。

K仅阳性检查，不进入主次池Q1/Q2。

K-001：实际盲审38条，A类28条。

K-002：实际盲审0条，A类0条。


首答及分支说明：

K-001：{"correct": 15, "format_missing_only": 1, "parsed_wrong": 0, "truncated": 0, "looped": 0, "format_missing": 1, "format_reasons": {"negated_or_nonunique_entity": 1}, "multiline_same_value": 0, "confusion_d": 0, "confusion_denominator": 0, "confusion_rate": null, "p0": 0.9375}；选中正确首答路径4，自然错误路径0。

K-002：{"parsed_wrong": 16, "correct": 0, "format_missing_only": 0, "truncated": 0, "looped": 0, "format_missing": 0, "format_reasons": {}, "multiline_same_value": 0, "confusion_d": 0, "confusion_denominator": 16, "confusion_rate": 0.0, "p0": 0.0}；选中正确首答路径0，自然错误路径2。

K-002没有有效正确首答，未产生正确路径S/C；该题没有A不能解释为模型面对正确首答后的坚持。K两题各有A的预测未成立，而至少1条A的继续门槛达到。
