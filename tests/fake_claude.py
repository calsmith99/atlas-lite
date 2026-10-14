#!/usr/bin/env python3
"""A local stream-protocol peer: never calls a model or performs tools."""
import json
import sys

def emit(e):
    print(json.dumps(e), flush=True)

def result():
    emit({'type':'result','usage':{'input_tokens':12,'output_tokens':8},'total_cost_usd':0.001})

mode = ''
for raw in sys.stdin:
    e = json.loads(raw)
    if e['type'] == 'user':
        mode = e['message']['content']
        if mode in ('hold', 'ignore'):
            continue
        if mode in ('permission', 'question'):
            inp = {'command':'echo approved'} if mode == 'permission' else {'questions':[{'question':'Proceed?', 'options':[{'label':'Yes'},{'label':'No'}]}]}
            emit({'type':'control_request','request_id':'request-1','request':{'subtype':'can_use_tool','tool_name':'Bash' if mode == 'permission' else 'AskUserQuestion','input':inp}})
        else:
            emit({'type':'stream_event','event':{'delta':{'type':'text_delta','text':mode}}})
            result()
    elif e['type'] == 'control_response':
        emit({'type':'stream_event','event':{'delta':{'type':'text_delta','text':json.dumps(e['response']['response'])}}})
        # A denied request can be followed by an interrupt; mimic that suspended turn.
        if e['response']['response']['behavior'] == 'allow':
            result()
    elif e['type'] == 'control_request' and e['request']['subtype'] == 'initialize':
        emit({'type':'control_response','response':{'subtype':'success','request_id':e['request_id'],'response':{}}})
    elif e['type'] == 'control_request' and mode != 'ignore':
        result()
