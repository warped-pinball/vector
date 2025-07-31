import ast
import sys
import types

# Define decorator stub
add_route = lambda *args, **kwargs: (lambda f: f)

# Stub modules used inside function
sys.modules['ubinascii'] = types.ModuleType('ubinascii')
sys.modules['ubinascii'].b2a_base64 = lambda x: b''
sys.modules['ubinascii'].a2b_base64 = lambda x: b''
sys.modules['ubinascii'].unhexlify = lambda x: b''

sys.modules['ujson'] = types.ModuleType('ujson')
sys.modules['ujson'].dumps = lambda *args, **kwargs: ''
sys.modules['ujson'].loads = lambda s: {}

sys.modules['curve25519'] = types.SimpleNamespace(generate_x25519_keypair=lambda: (None, None))

rsa_module = types.ModuleType('rsa')
rsa_module.key = types.SimpleNamespace(PublicKey=lambda **kwargs: None)
rsa_module.pkcs1 = types.SimpleNamespace(verify=lambda *args, **kwargs: None)
sys.modules['rsa'] = rsa_module
sys.modules['rsa.key'] = rsa_module.key
sys.modules['rsa.pkcs1'] = rsa_module.pkcs1

ws_module = types.ModuleType('websocket_client')
def fake_connect(url):
    raise Exception('connection failed')
ws_module.connect = fake_connect
sys.modules['websocket_client'] = ws_module

# Load backend.py and extract app_enable_origin
with open('src/common/backend.py', 'r') as f:
    source = f.read()
module_ast = ast.parse(source)
func_node = None
for node in module_ast.body:
    if isinstance(node, ast.FunctionDef) and node.name == 'app_enable_origin':
        func_node = node
        break
assert func_node is not None
module = ast.Module([func_node], type_ignores=[])
code = compile(module, filename='app_enable_origin', mode='exec')
namespace = {'add_route': add_route}
exec(code, namespace)
app_enable_origin = namespace['app_enable_origin']


def test_enable_origin_unreachable():
    result, status = app_enable_origin({})
    assert status == 503
    assert result['error'] == 'unreachable'
