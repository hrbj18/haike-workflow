"""Validate ComfyUI literals, links and selected V3 dynamic input branches."""
def fields(schema, values):
    result=[]
    def ordered(inputs):
        return [(k,v,group=='optional') for group in ('required','optional') for k,v in inputs.get(group,{}).items()]
    def add(name,spec,optional):
        raw=spec[0];opts=spec[1] if len(spec)>1 and isinstance(spec[1],dict) else {}
        if opts.get('hidden') and name not in values:return
        if raw=='COMFY_DYNAMICCOMBO_V3':
            choices=opts.get('options',[]);selected=values.get(name,choices[0]['key'] if choices else '')
            branch=next((x for x in choices if x['key']==selected),None)
            if branch is None:raise ValueError('未知动态分支 '+name)
            result.append((name,[[x['key'] for x in choices]],optional))
            for k,v,o in ordered(branch.get('inputs',{})):add(name+'.'+k,v,o)
        elif raw=='COMFY_AUTOGROW_V3':
            children=ordered(opts.get('template',{}).get('input',{}))
            child=children[0][1] if children else ['*']
            for k in values:
                if k.startswith(name+'.'):result.append((k,child,True))
        else:result.append((name,spec,optional))
    for k,v,o in ordered(schema.get('input',{})):add(k,v,o)
    return result

def check(graph, schemas):
    errors=[];links=enums=0
    for nid,n in graph.items():
        kind=n['class_type'];schema=schemas.get(kind)
        if schema is None:errors.append(nid+':缺少节点 '+kind);continue
        values=n.get('inputs',{})
        try:specs=fields(schema,values)
        except ValueError as e:errors.append(nid+':'+str(e));continue
        for name,spec,optional in specs:
            if name not in values:
                if not optional:errors.append(nid+'.'+name+':缺少必填输入')
                continue
            value=values[name];raw=spec[0];opts=spec[1] if len(spec)>1 and isinstance(spec[1],dict) else {}
            expected='COMBO' if isinstance(raw,list) else raw
            if isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and isinstance(value[1],int):
                links+=1;origin,slot=value
                if origin not in graph:errors.append(nid+'.'+name+':悬空连线');continue
                outputs=schemas.get(graph[origin]['class_type'],{}).get('output',[])
                if not 0<=slot<len(outputs):errors.append(nid+'.'+name+':输出槽越界');continue
                actual=outputs[slot]
                if actual not in ('*','COMFY_MATCHTYPE_V3') and expected not in ('*','COMFY_MATCHTYPE_V3') and actual not in expected.split(','):errors.append(nid+'.'+name+':连线类型不符')
                continue
            choices=raw if isinstance(raw,list) else opts.get('options') if raw=='COMBO' else None
            if choices and kind not in {'LoadImage','LoadAudio'}:
                enums+=1;allowed=[v.get('key') if isinstance(v,dict) else v for v in choices]
                if value not in allowed:errors.append(nid+'.'+name+':模型或枚举不可用')
            if expected=='INT' and (not isinstance(value,int) or isinstance(value,bool)):errors.append(nid+'.'+name+':须为整数')
            if expected=='FLOAT' and (not isinstance(value,(int,float)) or isinstance(value,bool)):errors.append(nid+'.'+name+':须为数值')
            if expected=='BOOLEAN' and not isinstance(value,bool):errors.append(nid+'.'+name+':须为布尔值')
            if expected=='STRING' and not isinstance(value,str):errors.append(nid+'.'+name+':须为字符串')
            if isinstance(value,(int,float)) and not isinstance(value,bool):
                if 'min' in opts and value<opts['min']:errors.append(nid+'.'+name+':低于最小值')
                if 'max' in opts and value>opts['max']:errors.append(nid+'.'+name+':高于最大值')
    return {'passed':not errors,'errors':errors,'nodes':len(graph),'links':links,'enums':enums}
