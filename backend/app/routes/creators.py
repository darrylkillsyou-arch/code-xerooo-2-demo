"""Creator routes for profiles, portfolios, achievements, and verifications."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import cast, String
from sqlalchemy.orm import Session, joinedload, selectinload
from app.database import get_db
from app.models.users import User
from app.models.creators import CreatorProfile, PortfolioItem, CreatorAchievement, Verification
from app.cache import cache, TTL_CREATORS_LIST, TTL_CREATOR_DETAIL
from app.schemas.creators import (
    CreatorProfileResponse,
    CreatorCardResponse,
    CreatorDetailResponse,
    CreatorProfileUpdate,
    PortfolioItemCreate,
    PortfolioItemResponse,
)
from app.dependencies import get_current_user, get_current_creator_user

router = APIRouter(prefix="/creators", tags=["creators"])


@router.get("", response_model=List[CreatorCardResponse])
def list_creators(
    skip: int = 0,
    limit: int = 200,
    query: Optional[str] = Query(None, description="Free text search query"),
    category: Optional[str] = Query(None, description="Discipline/core category filter"),
    specialization: Optional[str] = Query(None, description="Sub-specialization filter"),
    style: Optional[str] = Query(None, description="Style tag filter"),
    availability: Optional[str] = None,
    tools: Optional[str] = None,
    min_rate: Optional[float] = None,
    max_rate: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """Lists creator profiles with rich taxonomy, sub-specialization, style, and search filtering."""
    # Cache only unfiltered list (the most common Discover page load)
    is_unfiltered = not any([query, category and category.lower() not in ('all', 'all specialties'),
                             specialization, style, tools, min_rate, max_rate])
    cache_key = "creators:list:all"
    if is_unfiltered:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    q = (
        db.query(CreatorProfile)
        .join(User)
        .options(
            joinedload(CreatorProfile.user),
            selectinload(CreatorProfile.portfolio_items),
        )
        .filter(User.is_active == True)
    )

    if availability:
        q = q.filter(CreatorProfile.availability_status == availability)

    if min_rate is not None:
        q = q.filter(CreatorProfile.starting_rate >= min_rate)

    if max_rate is not None:
        q = q.filter(CreatorProfile.starting_rate <= max_rate)

    # Core Category Mapping (with legacy alias support)
    CATEGORY_ALIASES = {
        "all": None,
        "all specialties": None,
        "ai video": "AI Video",
        "ai videos": "AI Video",
        "video": "AI Video",
        "videos": "AI Video",
        "ai image": "AI Images",
        "ai images": "AI Images",
        "image": "AI Images",
        "images": "AI Images",
        "3d": "3D & CGI",
        "cgi": "3D & CGI",
        "3d & cgi": "3D & CGI",
        "3d/cgi": "3D & CGI",
        "product": "Product Advertising",
        "product ads": "Product Advertising",
        "product advertising": "Product Advertising",
        "fashion": "Fashion",
        "social": "Social Media",
        "social media": "Social Media",
        "animation": "Animation & Motion",
        "animation & motion": "Animation & Motion",
        "motion": "Animation & Motion",
        "graphic design": "Branding & Design",
        "branding": "Branding & Design",
        "branding & design": "Branding & Design",
        "branding & graphic design": "Branding & Design",
        "design": "Branding & Design",
        "audio": "Audio & Voice",
        "voice": "Audio & Voice",
        "audio & voice": "Audio & Voice",
    }

    if category:
        cat_clean = category.lower().strip()
        matched_core = CATEGORY_ALIASES.get(cat_clean, category)
        if matched_core:
            q = q.filter(
                (CreatorProfile.core_category == matched_core) |
                (CreatorProfile.specialization.ilike(f"%{matched_core}%"))
            )

    if specialization:
        spec_term = specialization.strip()
        q = q.filter(
            (CreatorProfile.specialization.ilike(f"%{spec_term}%")) |
            (cast(CreatorProfile.sub_specializations, String).ilike(f"%{spec_term}%")) |
            (cast(CreatorProfile.skills, String).ilike(f"%{spec_term}%"))
        )

    if style:
        style_term = style.strip()
        q = q.filter(
            (cast(CreatorProfile.style_tags, String).ilike(f"%{style_term}%")) |
            (CreatorProfile.tagline.ilike(f"%{style_term}%")) |
            (CreatorProfile.specialization.ilike(f"%{style_term}%"))
        )

    if tools:
        tool_term = tools.strip()
        q = q.filter(cast(CreatorProfile.ai_tools, String).ilike(f"%{tool_term}%"))

    creators = q.order_by(CreatorProfile.rating.desc(), CreatorProfile.sla_score.desc()).all()

    if query and query.strip():
        import re
        raw_query = query.lower().strip()
        stopwords = {
            "find", "search", "looking", "for", "a", "an", "the", "in", "with",
            "me", "want", "need", "to", "who", "can", "make", "create", "show",
            "get", "help", "please", "some", "good", "best", "top", "of", "and", "or",
            "creator", "creators", "director", "directors", "artist", "artists", "work"
        }
        tokens = [t for t in re.findall(r'[a-z0-9+#.-]+', raw_query) if len(t) > 1]
        meaningful_tokens = [t for t in tokens if t not in stopwords]

        if not meaningful_tokens:
            return creators[skip : skip + limit]

        # Domain stop-tokens that apply globally across almost all creators in this AI marketplace
        generic_tokens = {"ai", "generative", "content", "production", "studio", "works", "lab", "director"}

        # Distinctive tokens that narrow down domain intent
        discriminative_tokens = [t for t in meaningful_tokens if t not in generic_tokens]
        # If all tokens were generic (e.g. user literally searched "AI"), use all
        filter_tokens = discriminative_tokens if discriminative_tokens else meaningful_tokens

        synonym_groups = {
            "video": ["video", "cinematic", "film", "cinema", "runway", "camera", "sora", "kling", "vfx"],
            "fashion": ["fashion", "couture", "dress", "organza", "gown", "silk", "textile", "model", "lookbook", "apparel", "wear", "fabric", "drape", "bridal"],
            "3d": ["3d", "cgi", "spatial", "render", "unreal", "blender", "cinema 4d", "sneaker", "product render", "interior", "architecture"],
            "audio": ["audio", "sound", "music", "sonic", "voice", "voiceover", "podcast", "jingle", "soundtrack", "elevenlabs", "suno", "dubbing"],
            "product": ["product", "ecommerce", "packaging", "commercial", "bottle", "mockup", "item"],
            "advertising": ["advertising", "commercial", "campaign", "ad", "ads", "billboard", "marketing"],
            "luxury": ["luxury", "perfume", "fragrance", "couture", "high-end", "premium", "editorial"],
            "automotive": ["automotive", "car", "hypercar", "vehicle", "automobile", "racing"],
            "social": ["social", "instagram", "reels", "tiktok", "youtube", "thumbnail", "thumbnails", "carousel", "viral", "influencer", "post", "posts", "meme"],
            "animation": ["animation", "animated", "motion graphics", "2d", "anime", "manga", "cartoon", "explainer", "kinetic", "typography"],
            "design": ["design", "graphic", "branding", "identity", "logo", "typography", "packaging", "print", "infographic", "poster"],
        }

        # Expand specific discriminative tokens into precise domain terms
        expanded_tokens = set(meaningful_tokens)
        for token in filter_tokens:
            for group, words in synonym_groups.items():
                if token in words:
                    expanded_tokens.update(words[:4])

        scored_creators = []
        for c in creators:
            # Token matching targets
            name_text = (c.display_name or "").lower()
            core_text = (getattr(c, 'core_category', '') or "").lower()
            spec_text = (c.specialization or "").lower()
            subs_text = " ".join(getattr(c, 'sub_specializations', []) or []).lower()
            skills_text = " ".join(c.skills or []).lower()
            tools_text = " ".join(c.ai_tools or []).lower()
            styles_text = " ".join(getattr(c, 'style_tags', []) or []).lower()
            tagline_text = (c.tagline or "").lower()
            bio_text = (c.user.bio if c.user and c.user.bio else "").lower()

            # Multi-token precision gate:
            # Check if creator has relevant domain/keyword connection to the filter tokens
            has_domain_match = False
            matched_count = 0

            for dt in filter_tokens:
                token_matched = (
                    dt in name_text or dt in core_text or dt in spec_text or
                    dt in subs_text or dt in skills_text or dt in tools_text or
                    dt in styles_text or dt in tagline_text
                )
                if not token_matched:
                    # Check domain synonym match
                    for group, words in synonym_groups.items():
                        if dt in words:
                            if (group in core_text or group in spec_text or
                                any(w in spec_text or w in subs_text for w in words[:3])):
                                token_matched = True
                                break
                if token_matched:
                    matched_count += 1

            # Precision rule:
            # If 1 token: must match that token or its domain group
            # If 2 tokens: must match at least 1 token AND either (core/spec match or both tokens)
            # If 3+ tokens (e.g. "automotive product ad"): must match at least 2 tokens
            if len(filter_tokens) == 1:
                has_domain_match = (matched_count >= 1)
            elif len(filter_tokens) == 2:
                has_domain_match = (matched_count >= 2) or (matched_count >= 1 and any(dt in core_text or dt in spec_text for dt in filter_tokens))
            else:
                has_domain_match = (matched_count >= 2)

            if not has_domain_match:
                continue

            # Hierarchical Scoring
            score = 0.0

            for term in meaningful_tokens:
                # 1. Exact Name match (highest signal)
                if term in name_text:
                    score += 25.0
                # 2. Core Category match
                if term in core_text:
                    score += 20.0
                # 3. Specialization / Sub-specialization match
                if term in spec_text or term in subs_text:
                    score += 15.0
                # 4. Tool match
                if any(term in str(t).lower() for t in (c.ai_tools or [])):
                    score += 12.0
                # 5. Skills & Tagline match
                if term in skills_text or term in styles_text:
                    score += 8.0
                # 6. Bio & Tagline
                if term in tagline_text or term in bio_text:
                    score += 4.0

            # Bonus for matching multiple discriminative tokens (AND-intent boost)
            matched_filter_count = sum(
                1 for dt in filter_tokens
                if (dt in name_text or dt in core_text or dt in spec_text or
                    dt in subs_text or dt in tools_text or dt in skills_text)
            )
            if len(filter_tokens) > 1 and matched_filter_count == len(filter_tokens):
                score += 25.0  # Perfect multi-token intersection bonus
            elif matched_filter_count > 1:
                score += 10.0

            # Synonym resonance (small secondary bump)
            for exp in expanded_tokens:
                if exp in spec_text or exp in subs_text or exp in tools_text:
                    score += 1.5

            if score > 0:
                scored_creators.append((score, c))

        if scored_creators:
            scored_creators.sort(
                key=lambda x: (x[0], x[1].rating or 0, x[1].sla_score or 0),
                reverse=True
            )
            creators = [c for _, c in scored_creators]
        else:
            creators = []


    result = creators[skip : skip + limit]
    # Build lightweight card responses to reduce payload size
    card_responses = []
    for c in result:
        hero = c.portfolio_items[0].image_url if c.portfolio_items else None
        card = CreatorCardResponse(
            id=c.id,
            user_id=c.user_id,
            display_name=c.display_name,
            tagline=c.tagline,
            specialization=c.specialization,
            core_category=c.core_category,
            sub_specializations=c.sub_specializations or [],
            style_tags=c.style_tags or [],
            skills=c.skills or [],
            ai_tools=c.ai_tools or [],
            starting_rate=c.starting_rate,
            delivery_days=c.delivery_days,
            commercial_rights=c.commercial_rights,
            availability_status=c.availability_status,
            rating=c.rating,
            total_briefs=c.total_briefs,
            sla_score=c.sla_score,
            on_time_percentage=c.on_time_percentage,
            is_verified=c.is_verified,
            location=c.location,
            created_at=c.created_at,
            avatar_url=c.user.avatar_url if c.user else None,
            user_full_name=c.user.full_name if c.user else None,
            hero_image_url=hero,
        )
        card_responses.append(card)
    if is_unfiltered:
        cache.set(cache_key, card_responses, TTL_CREATORS_LIST)
    return card_responses


@router.get("/{creator_id}", response_model=CreatorDetailResponse)
def get_creator_detail(creator_id: int, db: Session = Depends(get_db)):
    """Retrieves full creator profile details including portfolio, achievements, and verifications."""
    cache_key = f"creator:detail:{creator_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    creator = (
        db.query(CreatorProfile)
        .options(
            joinedload(CreatorProfile.user),
            selectinload(CreatorProfile.portfolio_items),
            selectinload(CreatorProfile.achievements),
            selectinload(CreatorProfile.verifications),
        )
        .filter(CreatorProfile.id == creator_id)
        .first()
    )
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    result = CreatorDetailResponse.model_validate(creator)
    cache.set(cache_key, result, TTL_CREATOR_DETAIL)
    return result


@router.get("/{creator_id}/portfolio", response_model=List[PortfolioItemResponse])
def get_creator_portfolio(creator_id: int, db: Session = Depends(get_db)):
    """Retrieves portfolio items for a specific creator."""
    creator = db.query(CreatorProfile).filter(CreatorProfile.id == creator_id).first()
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    return db.query(PortfolioItem).filter(PortfolioItem.creator_id == creator_id).order_by(PortfolioItem.created_at.desc()).all()


@router.put("/profile", response_model=CreatorProfileResponse)
def update_my_creator_profile(
    profile_in: CreatorProfileUpdate,
    current_user: User = Depends(get_current_creator_user),
    db: Session = Depends(get_db),
):
    """Updates the authenticated creator's profile details."""
    creator = db.query(CreatorProfile).filter(CreatorProfile.user_id == current_user.id).first()
    if not creator:
        creator = CreatorProfile(user_id=current_user.id, display_name=current_user.full_name, specialization="AI Visual Artist")
        db.add(creator)

    update_data = profile_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(creator, field, value)

    db.commit()
    db.refresh(creator)
    return creator


@router.post("/portfolio", response_model=PortfolioItemResponse, status_code=status.HTTP_201_CREATED)
def add_portfolio_item(
    item_in: PortfolioItemCreate,
    current_user: User = Depends(get_current_creator_user),
    db: Session = Depends(get_db),
):
    """Adds a new portfolio item to the creator's showcase."""
    creator = db.query(CreatorProfile).filter(CreatorProfile.user_id == current_user.id).first()
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator profile not found")

    new_item = PortfolioItem(
        creator_id=creator.id,
        title=item_in.title,
        description=item_in.description,
        image_url=item_in.image_url,
        category=item_in.category,
        tools_used=item_in.tools_used,
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item
