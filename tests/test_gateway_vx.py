"""Pruebas I1-VX — Dialecto Schema v2-ext y Percepción Multimodal (SPEC-i1-vx).

Verifica la ampliación acotada de ADR-004 autorizada en ADR-008 §1:
- enum escalar
- minimum y maximum numéricos finitos
- array de profundidad 1 (escalares u objetos planos) con minItems/maxItems
- object anidado nivel 1
- rechazos fail-closed (profundidad > 1, $ref, claves extra)
- percepción multimodal estructurada (imagen + schema, audio + schema)
"""

import base64
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import gateway_core  # noqa: E402
from gateway_core import (  # noqa: E402
    ErrorV2, validar_payload, validar_salida, validar_schema,
)

try:
    from tests.test_gateway_i1 import GatewayBase  # noqa: E402
except ImportError:
    from test_gateway_i1 import GatewayBase  # noqa: E402


class SchemaV2ExtUnidad(unittest.TestCase):
    """Validación unitaria de esquemas con validar_schema (SPEC-i1-vx §2.1)."""

    def test_vx1_enum_escalar_valido(self):
        s = {
            "type": "object",
            "properties": {
                "color": {"type": "string", "enum": ["rojo", "verde", "azul"]},
                "nivel": {"type": "integer", "enum": [1, 2, 3]},
                "activo": {"type": "boolean", "enum": [True, False]},
            },
            "required": ["color"],
        }
        validar_schema(s)

    def test_vx1b_enum_invalido_rechaza_400(self):
        casos = [
            # tipo discordante en enum
            {"type": "string", "enum": ["rojo", 42]},
            # bool en enum integer
            {"type": "integer", "enum": [1, True]},
            # lista vacía
            {"type": "string", "enum": []},
            # elementos duplicados
            {"type": "string", "enum": ["a", "a"]},
            # duplicados float/int en number
            {"type": "number", "enum": [1, 1.0]},
            # enum no lista
            {"type": "string", "enum": "rojo"},
            # más de 32 elementos
            {"type": "integer", "enum": list(range(33))},
        ]
        for def_prop in casos:
            with self.subTest(def_prop=def_prop):
                s = {"type": "object", "properties": {"campo": def_prop}}
                with self.assertRaises(ErrorV2) as ctx:
                    validar_schema(s)
                self.assertEqual(ctx.exception.status, 400)
                self.assertEqual(ctx.exception.code, "unsupported_schema")

    def test_vx2_min_max_numerico_valido(self):
        s = {
            "type": "object",
            "properties": {
                "edad": {"type": "integer", "minimum": 0, "maximum": 120},
                "probabilidad": {
                    "type": "number", "minimum": 0.0, "maximum": 1.0,
                },
            },
        }
        validar_schema(s)

    def test_vx2b_min_max_invalido_rechaza_400(self):
        casos = [
            # minimum mayor que maximum
            {"type": "integer", "minimum": 10, "maximum": 5},
            # bool en minimum
            {"type": "integer", "minimum": True, "maximum": 10},
            # minimum en string
            {"type": "string", "minimum": 5},
            # cota no numérica
            {"type": "number", "minimum": "cero"},
            # nan o inf en cotas
            {"type": "number", "minimum": float("nan")},
            {"type": "number", "maximum": float("inf")},
        ]
        for def_prop in casos:
            with self.subTest(def_prop=def_prop):
                s = {"type": "object", "properties": {"campo": def_prop}}
                with self.assertRaises(ErrorV2) as ctx:
                    validar_schema(s)
                self.assertEqual(ctx.exception.status, 400)
                self.assertEqual(ctx.exception.code, "unsupported_schema")

    def test_vx3_array_escalares_valido(self):
        s = {
            "type": "object",
            "properties": {
                "etiquetas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 10,
                },
                "puntuaciones": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": 100},
                },
            },
        }
        validar_schema(s)

    def test_vx3b_array_invalido_rechaza_400(self):
        casos = [
            # items ausente
            {"type": "array"},
            # minItems mayor que maxItems
            {"type": "array", "items": {"type": "string"},
             "minItems": 5, "maxItems": 2},
            # maxItems > 64
            {"type": "array", "items": {"type": "string"}, "maxItems": 65},
            # minItems negativo
            {"type": "array", "items": {"type": "string"}, "minItems": -1},
            # array dentro de array (profundidad > 1)
            {"type": "array", "items": {"type": "array",
                                         "items": {"type": "string"}}},
        ]
        for def_prop in casos:
            with self.subTest(def_prop=def_prop):
                s = {"type": "object", "properties": {"campo": def_prop}}
                with self.assertRaises(ErrorV2) as ctx:
                    validar_schema(s)
                self.assertEqual(ctx.exception.status, 400)
                self.assertEqual(ctx.exception.code, "unsupported_schema")

    def test_vx4_array_objetos_planos_valido(self):
        s = {
            "type": "object",
            "properties": {
                "usuarios": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "nombre": {"type": "string"},
                        },
                        "required": ["id", "nombre"],
                    },
                    "minItems": 0,
                    "maxItems": 20,
                }
            },
        }
        validar_schema(s)

    def test_vx5_object_anidado_nivel_1_valido(self):
        s = {
            "type": "object",
            "properties": {
                "datos_usuario": {
                    "type": "object",
                    "properties": {
                        "nombre": {"type": "string"},
                        "activo": {"type": "boolean"},
                    },
                    "required": ["nombre"],
                }
            },
        }
        validar_schema(s)

    def test_vx6_rechazo_profundidad_mayor_1_y_ref(self):
        casos = [
            # object dentro de object (profundidad 2)
            {
                "type": "object",
                "properties": {
                    "sub1": {
                        "type": "object",
                        "properties": {
                            "sub2": {
                                "type": "object",
                                "properties": {"k": {"type": "string"}},
                            }
                        },
                    }
                },
            },
            # array dentro de object dentro de array
            {
                "type": "object",
                "properties": {
                    "lista": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                }
                            },
                        },
                    }
                },
            },
            # $ref prohibido
            {
                "type": "object",
                "properties": {"ref": {"$ref": "#/definitions/X"}},
            },
            # additionalProperties prohibido
            {
                "type": "object",
                "properties": {"k": {"type": "string"}},
                "additionalProperties": False,
            },
            # type no string (lista o dict) a nivel raíz
            {"type": "object", "properties": {"k": {"type": ["string"]}}},
            {"type": "object", "properties": {"k": {"type": {"a": 1}}}},
            # type no string dentro de objeto anidado
            {
                "type": "object",
                "properties": {
                    "sub": {
                        "type": "object",
                        "properties": {"k": {"type": ["string"]}},
                    }
                },
            },
            {
                "type": "object",
                "properties": {
                    "sub": {
                        "type": "object",
                        "properties": {"k": {"type": {"a": 1}}},
                    }
                },
            },
            # type no string dentro de array de objetos
            {
                "type": "object",
                "properties": {
                    "lista": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"k": {"type": ["string"]}},
                        },
                    }
                },
            },
            {
                "type": "object",
                "properties": {
                    "lista": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"k": {"type": {"a": 1}}},
                        },
                    }
                },
            },
            # sub-objeto con más de 16 propiedades
            {
                "type": "object",
                "properties": {
                    "sub": {
                        "type": "object",
                        "properties": {
                            f"p{i}": {"type": "string"} for i in range(17)
                        },
                    }
                },
            },
        ]
        for s in casos:
            with self.subTest(s=s):
                with self.assertRaises(ErrorV2) as ctx:
                    validar_schema(s)
                self.assertEqual(ctx.exception.status, 400)
                self.assertEqual(ctx.exception.code, "unsupported_schema")


class SalidaV2ExtUnidad(unittest.TestCase):
    """Validación unitaria de la salida del modelo con validar_salida."""

    def test_vx1_salida_enum(self):
        s = {
            "type": "object",
            "properties": {
                "color": {"type": "string", "enum": ["rojo", "azul"]},
            },
            "required": ["color"],
        }
        self.assertEqual(validar_salida('{"color": "rojo"}', s), "valid")
        with self.assertRaises(ErrorV2) as ctx:
            validar_salida('{"color": "verde"}', s)
        self.assertEqual(ctx.exception.status, 502)

    def test_vx1c_salida_enum_number_equivalente(self):
        s = {
            "type": "object",
            "properties": {"val": {"type": "number", "enum": [0.0, 1.5]}},
            "required": ["val"],
        }
        self.assertEqual(validar_salida('{"val": 0}', s), "valid")
        self.assertEqual(validar_salida('{"val": 1.5}', s), "valid")
        with self.assertRaises(ErrorV2):
            validar_salida('{"val": 2}', s)

    def test_vx2_salida_min_max(self):
        s = {
            "type": "object",
            "properties": {
                "edad": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "required": ["edad"],
        }
        self.assertEqual(validar_salida('{"edad": 25}', s), "valid")
        with self.assertRaises(ErrorV2):
            validar_salida('{"edad": -1}', s)
        with self.assertRaises(ErrorV2):
            validar_salida('{"edad": 101}', s)
        with self.assertRaises(ErrorV2):
            validar_salida('{"edad": true}', s)

    def test_vx3_salida_array_escalar(self):
        s = {
            "type": "object",
            "properties": {
                "valores": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 10},
                    "minItems": 1,
                    "maxItems": 3,
                }
            },
            "required": ["valores"],
        }
        self.assertEqual(validar_salida('{"valores": [10, 20]}', s), "valid")
        # excede maxItems
        with self.assertRaises(ErrorV2):
            validar_salida('{"valores": [10, 20, 30, 40]}', s)
        # elemento menor que minimum
        with self.assertRaises(ErrorV2):
            validar_salida('{"valores": [5]}', s)

    def test_vx4_salida_object_anidado_estricto(self):
        s = {
            "type": "object",
            "properties": {
                "persona": {
                    "type": "object",
                    "properties": {
                        "nombre": {"type": "string"},
                        "edad": {"type": "integer"},
                    },
                    "required": ["nombre"],
                }
            },
            "required": ["persona"],
        }
        self.assertEqual(
            validar_salida('{"persona": {"nombre": "Ana", "edad": 30}}', s),
            "valid",
        )
        # falta required
        with self.assertRaises(ErrorV2):
            validar_salida('{"persona": {"edad": 30}}', s)
        # clave extra en el objeto anidado rechaza 502
        with self.assertRaises(ErrorV2):
            validar_salida('{"persona": {"nombre": "Ana", "extra": 1}}', s)

    def test_vx3b_salida_array_sin_maxitems_supera_64_falla_502(self):
        s = {
            "type": "object",
            "properties": {
                "vals": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["vals"],
        }
        salida_65 = json.dumps({"vals": list(range(65))})
        with self.assertRaises(ErrorV2) as ctx:
            validar_salida(salida_65, s)
        self.assertEqual(ctx.exception.status, 502)

    def test_vx5_salida_array_objetos_planos(self):
        s = {
            "type": "object",
            "properties": {
                "usuarios": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "nombre": {"type": "string"},
                        },
                        "required": ["id"],
                    },
                }
            },
            "required": ["usuarios"],
        }
        self.assertEqual(
            validar_salida('{"usuarios": [{"id": 1, "nombre": "A"}]}', s),
            "valid",
        )
        # falta required id
        with self.assertRaises(ErrorV2):
            validar_salida('{"usuarios": [{"nombre": "A"}]}', s)
        # clave extra en objeto del array
        with self.assertRaises(ErrorV2):
            validar_salida('{"usuarios": [{"id": 1, "extra": True}]}', s)


class GatewayHttpVx(GatewayBase):
    """Integración de gateway con schema v2-ext y percepción multimodal."""

    def test_vx7_payload_con_schema_v2_ext_atraviesa(self):
        from tests.test_gateway_i1 import _BackendFalso
        schema = {
            "type": "object",
            "properties": {
                "opciones": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["a", "b"]},
                    "maxItems": 5,
                }
            },
            "required": ["opciones"],
        }
        _BackendFalso.canned = {
            "choices": [{
                "message": {"content": json.dumps({"opciones": ["a"]})}
            }]
        }
        estado, cuerpo = self.post({
            "messages": [{"role": "user", "content": "test"}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "resp", "schema": schema},
            },
        })
        self.assertEqual(estado, 200)
        self.assertEqual(self.contador(), 1)

    def test_vx8_multimodal_audio_con_schema_atraviesa(self):
        from tests.test_gateway_i1 import _BackendFalso
        wav = (b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
               b"\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00"
               b"data\x00\x00\x00\x00")
        b64 = base64.b64encode(wav).decode("ascii")
        schema = {
            "type": "object",
            "properties": {
                "intencion": {
                    "type": "string", "enum": ["saludo", "despedida"],
                },
                "confianza": {
                    "type": "number", "minimum": 0.0, "maximum": 1.0,
                },
            },
            "required": ["intencion"],
        }
        _BackendFalso.canned = {
            "choices": [{
                "message": {
                    "content": json.dumps(
                        {"intencion": "saludo", "confianza": 0.95}
                    )
                }
            }]
        }
        estado, cuerpo = self.post({
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": b64, "format": "wav"},
                    },
                    {"type": "text", "text": "Clasifica el audio."},
                ],
            }],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "clasificacion", "schema": schema},
            },
        })
        self.assertEqual(estado, 200)
        self.assertEqual(self.contador(), 1)


if __name__ == "__main__":
    unittest.main()
