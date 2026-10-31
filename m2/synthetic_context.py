"""Explicit isolated-preview fixtures, not Host identity or production IAM."""
from knowledge_core.core import Actor, BusinessContext

CASES = [
    {'question':'合成客服服务时间是什么？','expectedClause':'第一条'},
    {'question':'客户如何申请历史对账单？','expectedClause':'第二条'},
    {'question':'信息缺失时如何处理？','expectedClause':'第三条'},
]
AUTHOR = Actor('m2-isolated','producer','synthetic-authority-not-bank-approved', frozenset({
    'policy.manage','source.register','source.activate','gold.manage','recipe.edit',
    'artifact.produce','candidate.validate','document.approve','manifest.publish','binding.manage'}))
READER = Actor('m2-isolated','knowledge-agent','synthetic-host-not-production')
CONTEXT = BusinessContext('2026-10-30','CN-BJ','synthetic-bank','customer-service','evidence-query','frozen-synthetic-clock')
SCOPE = {'regions':['CN-BJ'],'institutions':['synthetic-bank'],'products':['customer-service'],
         'purposes':['evidence-query'],'validFrom':'2026-01-01','validTo':None,'timezone':'Asia/Shanghai'}
