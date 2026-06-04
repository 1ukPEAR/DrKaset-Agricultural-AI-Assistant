from fastapi import APIRouter

from market_price_service import get_market_prices

router = APIRouter(prefix="/market-prices", tags=["market-prices"])


@router.get("")
def market_prices():
    return get_market_prices()
