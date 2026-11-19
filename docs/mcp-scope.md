# SpecHeap — Alcance del MCP (MVP)

Estado: borrador v0.1 · Core en Python · Transporte `stdio`

## 1. Contexto

SpecHeap modela el proceso SDD como un grafo trazable:

```
Epic → Feature → Req → Spec → Verificación
```

El MCP permite que modelos de IA consulten y modifiquen ese grafo. Los humanos usan CLI y UI sobre el mismo core.

## 2. Principios

1. **La IA propone, el humano aprueba.** El MCP nunca puede aprobar.
2. **Pocas tools, orientadas a tareas** (~12). Cada tool extra consume contexto del modelo.
3. **Salida doble:** `structuredContent` (JSON validado con Pydantic) más un resumen corto en markdown.
4. **Errores accionables:** código, causa y siguiente paso sugerido.
5. **Concurrencia optimista:** cada ítem tiene `revision` (hash del contenido). `update_item` la exige para no pisar ediciones humanas.
6. **Auditoría:** cada escritura se registra en `.specheap/log.jsonl` con `actor`, tool, id y timestamp.
7. **Las reglas viven en el core, no en el MCP** (ver sección 9).

## 3. Transporte y ejecución

- `specheap mcp --root <ruta>`: servidor `stdio`.
- `--readonly`: no se registra ninguna tool de escritura.
- HTTP (Streamable) queda para el modo hosteado, fuera del MVP.

Ejemplo de configuración en un cliente:

```json
{
  "mcpServers": {
    "specheap": {
      "command": "uvx",
      "args": ["specheap", "mcp", "--root", "."]
    }
  }
}
```

## 4. Tools de lectura

| Tool | Entrada | Devuelve |
|---|---|---|
| `get_overview` | — | Conteo por tipo y estado, % de cobertura, nº de gaps y de ítems `stale` |
| `list_items` | `type?`, `status?`, `parent_id?`, `query?`, `limit`, `cursor` | Lista paginada (id, título, estado, parent) |
| `get_item` | `id` | Ítem completo, `revision` y enlaces directos |
| `get_context` | `id`, `depth?` | **Tool principal.** Ancestros hasta el Epic más descendientes (reqs, specs, verificaciones) con su estado, en un solo paquete |
| `trace` | `id`, `direction: up\|down\|both` | Cadena de trazabilidad Epic → … → Verificación |
| `list_gaps` | `scope_id?`, `kinds?` | Reqs sin spec, reqs sin verificación, specs sin verificación, ítems `stale`, verificaciones fallidas |
| `next_work` | `limit?` | Ítems `approved` listos para implementar, ordenados por dependencias |

## 5. Tools de escritura

Todas pasan por el ciclo de vida (sección 6).

| Tool | Entrada | Efecto |
|---|---|---|
| `create_item` | `type`, `parent_id`, `title`, `body`, `fields?` | Crea en `draft`. Valida tipo y padre (Feature→Epic, Req→Feature, Spec→Req, Verificación→Req/Spec) |
| `update_item` | `id`, `patch`, `expected_revision` | Edita. Si el ítem estaba `approved`, vuelve a `proposed` y marca sus dependientes como `stale` |
| `propose_item` | `id` | `draft → proposed` (solicita revisión humana) |
| `link_items` / `unlink_items` | `from_id`, `to_id`, `relation` | Relaciones: `satisfies` (Spec→Req), `verifies` (Verificación→Req/Spec). La jerarquía se expresa con `parent_id` |
| `mark_implemented` | `id`, `evidence?` | `approved → implemented` (Req o Spec) |
| `report_verification` | `id`, `result: pass\|fail\|skipped`, `evidence`, `run_ref?` | Registra el resultado de una verificación |

Un Req pasa a `verified` solo cuando **todas** sus verificaciones están en `pass`. Es un estado derivado y ninguna tool puede asignarlo.

## 6. Ciclo de vida y permisos

Estados: `draft → proposed → approved → implemented → verified`, más `stale` (requiere revisión tras un cambio aguas arriba).

| Transición | Agente (MCP) | Humano (CLI/UI) |
|---|---|---|
| crear → `draft` | ✅ | ✅ |
| `draft → proposed` | ✅ | ✅ |
| `proposed → approved` | ❌ | ✅ |
| `approved → implemented` | ✅ | ✅ |
| `→ verified` | derivado | derivado |
| limpiar `stale` | ❌ (solo editando, lo que reenvía a `proposed`) | ✅ |
| borrar / archivar | ❌ | ✅ |

Regla de integridad: todo Req debe tener ≥1 Spec y ≥1 Verificación para considerarse cubierto. `list_gaps` lo reporta.

## 7. Resources y Prompts

**Resources**
- `specheap://overview`
- `specheap://{type}/{id}`: ítem como markdown
- `specheap://feature/{id}/context`: equivalente a `get_context`

**Prompts**
- `decompose_feature(feature_id)`: genera Reqs en formato EARS
- `draft_specs(req_id)`: propone Specs técnicas para un Req
- `plan_verifications(req_id)`: propone Verificaciones con criterios medibles
- `review_gaps()`: recorre `list_gaps` y propone cómo cerrarlos

## 8. Contrato de errores

| Código | Cuándo |
|---|---|
| `NOT_FOUND` | El id no existe |
| `INVALID_PARENT` | Tipo de padre incompatible |
| `INVALID_TRANSITION` | Transición no permitida desde el estado actual |
| `FORBIDDEN_FOR_AGENT` | Acción reservada a humanos |
| `REVISION_CONFLICT` | `expected_revision` obsoleta (se devuelve la actual) |
| `VALIDATION_ERROR` | Campo inválido (indica campo y motivo) |
| `READONLY_MODE` | Escritura con `--readonly` |

Cada error incluye un campo `hint` con el siguiente paso sugerido.

## 9. Arquitectura: capa de servicio con actor

Las reglas (matriz de permisos, `revision`, propagación de `stale`, auditoría) se implementan en una **capa de servicio** dentro del core, parametrizada por actor:

```
MCP tools ─┐
CLI ───────┼─▶ Service(actor) ─▶ Storage (archivos .md + índice SQLite)
UI web ────┘
```

Las tools MCP son una capa fina que llama a `Service(actor="agent")`. Esto garantiza que ningún cliente pueda saltarse las reglas y permite añadir nuevas interfaces sin duplicar lógica.

## 10. Fuera del MVP

- Borrado y aprobación vía MCP.
- Import de resultados de tests (JUnit).
- Búsqueda semántica.
- Autenticación y multiusuario (HTTP).
- Diff entre versiones y notificaciones.

## 11. Evolución: code mode (v2)

Sobre la misma capa de servicio se podrá añadir un modo de **ejecución de código**: una tool `execute_script` más `search_api`, donde el modelo escribe un script Python contra una fachada tipada del servicio en lugar de encadenar llamadas.

Requisitos para v2:
- Sandbox de ejecución (subproceso con límites, contenedor o intérprete sandbox).
- La fachada hereda las restricciones de `Service(actor="agent")`; el script no puede importar el core completo.
- Auditoría por script (código ejecutado + efectos).

Beneficios: menos tokens, menos viajes y descubrimiento progresivo de la API. En local, mientras tanto, un agente con acceso a shell ya puede usar el CLI con `--json`.

## 12. Criterios de aceptación

1. Un agente (p. ej. Claude Code) descompone una Feature en Reqs → Specs → Verificaciones usando solo el MCP.
2. Intentar aprobar por MCP falla con `FORBIDDEN_FOR_AGENT`.
3. Editar un Req aprobado marca sus Specs y Verificaciones como `stale`.
4. `update_item` con una `revision` obsoleta devuelve `REVISION_CONFLICT`.
5. Con `--readonly` no se expone ninguna tool de escritura.
6. Cada tool tiene test de contrato (entrada/salida) con el cliente MCP de prueba del SDK.
7. Toda escritura aparece en `log.jsonl` con `actor: "agent"`.

## 13. Decisiones abiertas

- `mark_implemented` por el agente: permitido en este borrador. Pasar a humano si se quiere más control.
- `create_item` genérica (elegida para ahorrar tokens) frente a una tool por tipo con esquemas más específicos.
