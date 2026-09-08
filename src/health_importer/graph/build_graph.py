from __future__ import annotations

import warnings

from langchain_core._api.deprecation import (
    LangChainDeprecationWarning,
    LangChainPendingDeprecationWarning,
)

from health_importer.graph.state import (
    get_next_route,
    get_status,
)

warnings.filterwarnings(
    "ignore",
    message="The default value of `allowed_objects` will change in a future version.*",
    category=LangChainDeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message="The default value of `allowed_objects` will change in a future version.*",
    category=LangChainPendingDeprecationWarning,
)

from langgraph.graph import END, START, StateGraph

from health_importer.graph.anytype_update_nodes import update_kassen_anytype, update_pkv_anytype
from health_importer.graph.befund_nodes import (
    attach_befund_to_invoice,
    decide_befund_match,
    match_befund_invoice,
    move_befund_to_target,
    prepare_befund_target_filename,
    upload_befund_pdf,
)
from health_importer.graph.classification_nodes import route_by_document_type
from health_importer.graph.file_nodes import (
    rename_file_to_target,
    rename_kassen_file,
    rename_pkv_file,
)
from health_importer.graph.finalization_nodes import (
    cleanup_vision_temp,
    load_file_metadata,
    mark_finished,
    mark_started,
)
from health_importer.graph.invoice_nodes import (
    apply_manual_corrections,
    decide_import_route,
    execute_anytype_import,
    extract_structured_invoice,
    move_invoice_to_target,
    prepare_import_plan,
    validate_structured_invoice,
    verify_invoice_text_values,
    verify_structured_invoice,
)
from health_importer.graph.nodes import (
    create_pkv_draft,
    decide_kassen_match,
    decide_pkv_match,
    extract_kassen_ruckmeldung,
    extract_pkv_antwort,
    kassen_review_node,
    mark_pkv_review,
    match_kassen_invoice,
    match_pkv_invoice,
    move_kassen_to_done,
    move_pkv_to_done,
    prepare_kassen_target_filename,
    prepare_pkv_target_filename,
    upload_kassen_pdf_node,
    upload_pkv_pdf_node,
    validate_kassen_ruckmeldung_node,
    validate_pkv_antwort_node,
)
from health_importer.graph.pdf_nodes import (
    evaluate_embedded_text_quality,
    extract_embedded_pdf_text,
    render_vision_pages_if_needed,
    run_ocr_if_needed,
)
from health_importer.graph.state import GraphState


def build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("load_file_metadata", load_file_metadata)
    graph.add_node("mark_started", mark_started)
    graph.add_node("extract_embedded_pdf_text", extract_embedded_pdf_text)
    graph.add_node("evaluate_embedded_text_quality", evaluate_embedded_text_quality)
    graph.add_node("run_ocr_if_needed", run_ocr_if_needed)
    graph.add_node("render_vision_pages_if_needed", render_vision_pages_if_needed)
    graph.add_node("extract_structured_invoice", extract_structured_invoice)
    graph.add_node("route_by_document_type", route_by_document_type)
    graph.add_node("apply_manual_corrections", apply_manual_corrections)
    graph.add_node("verify_structured_invoice", verify_structured_invoice)
    graph.add_node("validate_structured_invoice", validate_structured_invoice)
    graph.add_node("verify_invoice_text_values", verify_invoice_text_values)
    graph.add_node("decide_import_route", decide_import_route)
    graph.add_node("prepare_import_plan", prepare_import_plan)
    graph.add_node("rename_file_to_target", rename_file_to_target)
    graph.add_node("execute_anytype_import", execute_anytype_import)
    graph.add_node("move_invoice_to_target", move_invoice_to_target)
    graph.add_node("mark_finished", mark_finished)
    # Kassen-Rückmeldung flow
    graph.add_node("extract_kassen_ruckmeldung", extract_kassen_ruckmeldung)
    graph.add_node("validate_kassen_ruckmeldung", validate_kassen_ruckmeldung_node)
    graph.add_node("match_kassen_invoice", match_kassen_invoice)
    graph.add_node("decide_kassen_match", decide_kassen_match)
    graph.add_node("prepare_kassen_target_filename", prepare_kassen_target_filename)
    graph.add_node("rename_kassen_file", rename_kassen_file)
    graph.add_node("upload_kassen_pdf", upload_kassen_pdf_node)
    graph.add_node("update_kassen_anytype", update_kassen_anytype)
    graph.add_node("kassen_review", kassen_review_node)
    graph.add_node("create_pkv_draft", create_pkv_draft)
    graph.add_node("move_kassen_to_done", move_kassen_to_done)
    # Befund / Patientenbrief flow
    graph.add_node("match_befund_invoice", match_befund_invoice)
    graph.add_node("decide_befund_match", decide_befund_match)
    graph.add_node("prepare_befund_target_filename", prepare_befund_target_filename)
    graph.add_node("upload_befund_pdf", upload_befund_pdf)
    graph.add_node("attach_befund_to_invoice", attach_befund_to_invoice)
    graph.add_node("move_befund_to_target", move_befund_to_target)
    # Pkv-Antwort flow
    graph.add_node("extract_pkv_antwort", extract_pkv_antwort)
    graph.add_node("validate_pkv_antwort", validate_pkv_antwort_node)
    graph.add_node("match_pkv_invoice", match_pkv_invoice)
    graph.add_node("decide_pkv_match", decide_pkv_match)
    graph.add_node("prepare_pkv_target_filename", prepare_pkv_target_filename)
    graph.add_node("rename_pkv_file", rename_pkv_file)
    graph.add_node("upload_pkv_pdf", upload_pkv_pdf_node)
    graph.add_node("update_pkv_anytype", update_pkv_anytype)
    graph.add_node("move_pkv_to_done", move_pkv_to_done)
    # Pkv review fallback (still needed for unclear matches)
    graph.add_node("mark_pkv_review", mark_pkv_review)
    graph.add_node("cleanup_vision_temp", cleanup_vision_temp)

    graph.add_edge(START, "load_file_metadata")
    graph.add_edge("load_file_metadata", "mark_started")
    graph.add_edge("mark_started", "extract_embedded_pdf_text")
    graph.add_edge("extract_embedded_pdf_text", "evaluate_embedded_text_quality")
    graph.add_edge("evaluate_embedded_text_quality", "run_ocr_if_needed")
    graph.add_edge("run_ocr_if_needed", "render_vision_pages_if_needed")
    graph.add_edge("render_vision_pages_if_needed", "extract_structured_invoice")
    graph.add_edge("extract_structured_invoice", "route_by_document_type")

    # Conditional routing after document type detection
    graph.add_conditional_edges(
        "route_by_document_type",
        _kassen_or_invoice_router,
        {
            "invoice_flow": "apply_manual_corrections",
            "kassen_flow": "extract_kassen_ruckmeldung",
            "pkv_flow": "extract_pkv_antwort",
            "befund_flow": "match_befund_invoice",
        },
    )

    # Invoice flow (existing)
    graph.add_edge("apply_manual_corrections", "verify_structured_invoice")
    graph.add_edge("verify_structured_invoice", "validate_structured_invoice")
    graph.add_edge("validate_structured_invoice", "verify_invoice_text_values")
    graph.add_edge("verify_invoice_text_values", "decide_import_route")
    graph.add_edge("decide_import_route", "prepare_import_plan")
    graph.add_edge("prepare_import_plan", "rename_file_to_target")
    graph.add_edge("rename_file_to_target", "execute_anytype_import")
    graph.add_edge("execute_anytype_import", "move_invoice_to_target")
    graph.add_edge("move_invoice_to_target", "mark_finished")

    # Kassen-Rückmeldung flow
    graph.add_edge("extract_kassen_ruckmeldung", "validate_kassen_ruckmeldung")
    graph.add_edge("validate_kassen_ruckmeldung", "match_kassen_invoice")
    graph.add_conditional_edges(
        "match_kassen_invoice",
        _kassen_status_router,
        {
            "auto": "prepare_kassen_target_filename",
            "decide": "decide_kassen_match",
        },
    )
    graph.add_conditional_edges(
        "decide_kassen_match",
        _kassen_decision_router,
        {
            "auto": "prepare_kassen_target_filename",
            "review": "kassen_review",
            "unclear": "kassen_review",
        },
    )
    graph.add_edge("prepare_kassen_target_filename", "rename_kassen_file")
    graph.add_edge("rename_kassen_file", "upload_kassen_pdf")
    graph.add_edge("upload_kassen_pdf", "update_kassen_anytype")
    graph.add_edge("update_kassen_anytype", "create_pkv_draft")
    graph.add_edge("create_pkv_draft", "move_kassen_to_done")
    graph.add_edge("move_kassen_to_done", "mark_finished")
    graph.add_edge("kassen_review", "mark_finished")

    # Befund flow: attach to the invoice object, or land in the error folder so
    # the document can be re-run once its invoice has been imported.
    graph.add_edge("match_befund_invoice", "decide_befund_match")
    graph.add_conditional_edges(
        "decide_befund_match",
        _befund_router,
        {
            "attach": "prepare_befund_target_filename",
            "no_match": "move_befund_to_target",
        },
    )
    graph.add_edge("prepare_befund_target_filename", "upload_befund_pdf")
    graph.add_edge("upload_befund_pdf", "attach_befund_to_invoice")
    graph.add_edge("attach_befund_to_invoice", "move_befund_to_target")
    graph.add_edge("move_befund_to_target", "mark_finished")

    # Pkv-Antwort flow
    graph.add_edge("extract_pkv_antwort", "validate_pkv_antwort")
    graph.add_edge("validate_pkv_antwort", "match_pkv_invoice")
    graph.add_conditional_edges(
        "match_pkv_invoice",
        _pkv_status_router,
        {
            "auto": "prepare_pkv_target_filename",
            "decide": "decide_pkv_match",
        },
    )
    graph.add_conditional_edges(
        "decide_pkv_match",
        _pkv_decision_router,
        {
            "auto": "prepare_pkv_target_filename",
            "review": "mark_pkv_review",
            "unclear": "mark_pkv_review",
        },
    )
    graph.add_edge("prepare_pkv_target_filename", "rename_pkv_file")
    graph.add_edge("rename_pkv_file", "upload_pkv_pdf")
    graph.add_edge("upload_pkv_pdf", "update_pkv_anytype")
    graph.add_edge("update_pkv_anytype", "move_pkv_to_done")
    graph.add_edge("move_pkv_to_done", "mark_finished")
    graph.add_edge("mark_pkv_review", "mark_finished")

    graph.add_edge("mark_finished", "cleanup_vision_temp")
    graph.add_edge("cleanup_vision_temp", END)
    return graph.compile()


def _befund_router(state: GraphState) -> str:
    return "attach" if get_next_route(state) == "befund_attach" else "no_match"


def _kassen_or_invoice_router(state: GraphState) -> str:
    return str(get_next_route(state))


def _kassen_decision_router(state: GraphState) -> str:
    route = get_next_route(state)
    if route == "kassen_auto_update":
        return "auto"
    if route == "kassen_review_match":
        return "review"
    return "unclear"


def _kassen_status_router(state: GraphState) -> str:
    """Route KASSEN_MATCHED_CORRECTED directly to auto, bypassing decide_kassen_match."""
    status = get_status(state)
    if status == "KASSEN_MATCHED_CORRECTED":
        return "auto"
    return "decide"


def _pkv_decision_router(state: GraphState) -> str:
    route = get_next_route(state)
    if route == "pkv_auto_update":
        return "auto"
    if route == "pkv_review_match":
        return "review"
    return "unclear"


def _pkv_status_router(state: GraphState) -> str:
    """Route PKV_MATCHED_CORRECTED directly to auto, bypassing decide_pkv_match."""
    status = get_status(state)
    if status == "PKV_MATCHED_CORRECTED":
        return "auto"
    return "decide"
