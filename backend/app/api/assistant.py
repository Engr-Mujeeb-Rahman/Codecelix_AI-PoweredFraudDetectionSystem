from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.schemas.assistant import AssistantQueryRequest, AssistantQueryResponse
from app.services.assistant import ask_investigation_assistant

router = APIRouter()


@router.post("/query", response_model=AssistantQueryResponse)
async def query_assistant(
    data: AssistantQueryRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """AI Investigation Assistant for fraud analysts (Requirement 14).

    Answers questions regarding customers, devices, investigations, and irregular activity
    grounded in actual platform database records.
    """
    answer, mode, ref_data = await ask_investigation_assistant(
        db=db,
        query=data.query,
        customer_id=data.customer_id,
        transaction_id=data.transaction_id,
        device_id=data.device_id,
        investigation_id=data.investigation_id,
    )
    return AssistantQueryResponse(
        query=data.query,
        answer=answer,
        mode=mode,
        referenced_data=ref_data,
    )
