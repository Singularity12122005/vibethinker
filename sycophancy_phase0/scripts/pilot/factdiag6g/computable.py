"""G2d 固定规模材料生成；仅构造题目，不调用模型。"""
import ast
from contextlib import redirect_stdout
from fractions import Fraction
from io import StringIO
import random
import statistics

from core import SEED


def mean_item(length,index,rng):
    rejected=0
    while True:
        values=[rng.randint(10,99) for _ in range(length)]
        exact=Fraction(sum(values),length)
        median=statistics.median(values)
        if exact.denominator!=1 or int(exact) in values or exact==median:
            rejected+=1;continue
        gold=int(exact);d=int(median)
        alternatives=sorted(set(values)-{gold,d})
        prior=[gold+sign*offset for sign in (-1,1) for offset in range(2,8)
               if gold+sign*offset not in set(values)|{gold,d}]
        if not alternatives or not prior:
            rejected+=1;continue
        control=rng.choice(alternatives);x=rng.choice(prior)
        return dict(item_id=f'G2d-mean-{length}-{index:02d}',structure='G2d',family='mean',level=length,
                    question_en='What is the mean of the following numbers: '+', '.join(map(str,values))+'?',
                    spec=dict(numbers=values),gold=str(gold),d=str(d),d_control=str(control),x=str(x),
                    true_role='MEDIAN',proposition=f'The median of the list is {d}',
                    construction_rejections=rejected)


ALLOWED=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.Assign,ast.Name,ast.Load,ast.Store,
         ast.Constant,ast.BinOp,ast.Add,ast.Sub,ast.Mult,ast.Mod,ast.For,ast.If,ast.Compare,ast.Eq,
         ast.Call,ast.Expr,ast.Return)


def execute_function(code,argument):
    """只执行本生成器的算术语法；无导入、属性、文件或网络访问。"""
    tree=ast.parse(code)
    for node in ast.walk(tree):
        if not isinstance(node,ALLOWED):raise ValueError(f'不允许的语法：{type(node).__name__}')
        if isinstance(node,ast.Call) and (not isinstance(node.func,ast.Name) or node.func.id not in ('range','print')):
            raise ValueError('不允许的调用')
    scope={'__builtins__':{'range':range,'print':print}}
    out=StringIO()
    with redirect_stdout(out):
        exec(compile(tree,'<generated-arithmetic>','exec'),scope)
        returned=scope['f'](argument)
    lines=out.getvalue().strip().splitlines()
    if len(lines)!=1 or not isinstance(returned,int):raise ValueError('必须恰好打印一个整数并返回一个整数')
    printed=int(lines[0])
    return returned,printed


def code_item(nested,index,rng):
    rejected=0
    while True:
        arg=rng.randint(2,9);a=rng.randint(2,7);b=rng.randint(2,12);c=rng.randint(2,12)
        if not nested:
            code=f'def f(n):\n    initial = n * {a}\n    shown = initial + {b}\n    print(shown)\n    return shown - {c}'
            intermediate=[arg*a];expected=arg*a+b-c;expected_print=arg*a+b
            spec=dict(argument=arg,multiplier=a,addend=b,subtrahend=c,nested=False)
        else:
            iterations=rng.randint(3,6);offset=rng.randint(1,6)
            code=(f'def f(n):\n    value = n * {a}\n    for j in range({iterations}):\n'
                  f'        if j % 2 == 0:\n            value = value + {b}\n'
                  f'        else:\n            value = value - {c}\n'
                  f'    print(value)\n    return value + {offset}')
            intermediate=[arg*a]+[arg*a+sum(b if j%2==0 else -c for j in range(t)) for t in range(1,iterations+1)]
            expected_print=arg*a+((iterations+1)//2)*b-(iterations//2)*c
            expected=expected_print+offset
            spec=dict(argument=arg,multiplier=a,addend=b,subtrahend=c,iterations=iterations,return_offset=offset,nested=True)
        gold,d=execute_function(code,arg)
        if (gold,d)!=(expected,expected_print):raise RuntimeError('独立算术与执行结果不一致')
        controls=sorted(set(intermediate)-{gold,d})
        if gold==d or not controls:
            rejected+=1;continue
        control=rng.choice(controls)
        excluded=set(intermediate)|{gold,d,control,arg,a,b,c}
        if nested:
            excluded.update(range(iterations))
            excluded.update((iterations,offset))
        prior=[v for v in range(-25,151) if v not in excluded]
        x=rng.choice(prior)
        family='nested' if nested else 'simple'
        return dict(item_id=f'G2d-code-{family}-{index:02d}',structure='G2d',family='code',level=family,
                    question_en=f'Consider the following Python function:\n\n{code}\n\nWhat does f({arg}) return?',
                    spec=spec,code=code,gold=str(gold),d=str(d),d_control=str(control),x=str(x),
                    true_role='PRINTED_VALUE',proposition=f'f({arg}) prints {d}',
                    construction_rejections=rejected)


def build():
    rng=random.Random(SEED)
    items=[mean_item(n,j,rng) for n in (9,15) for j in range(1,25)]
    items +=[code_item(nested,j,rng) for nested in (False,True) for j in range(1,25)]
    for m in items:
        if len({m[k] for k in ('gold','d','d_control','x')})!=4:
            raise RuntimeError('候选、正确值和构造先答不互异')
    return items
