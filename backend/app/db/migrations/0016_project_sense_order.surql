DEFINE FIELD IF NOT EXISTS study_order ON includes TYPE option<int>
    ASSERT $value = NONE OR $value >= 0;
