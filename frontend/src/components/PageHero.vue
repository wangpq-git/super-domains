<template>
  <section class="page-hero" :class="heroClass">
    <div class="page-hero__copy">
      <p v-if="eyebrow" class="page-hero__eyebrow">{{ eyebrow }}</p>
      <div class="page-hero__title-row">
        <div>
          <h1 class="page-hero__title">{{ title }}</h1>
          <p v-if="subtitle" class="page-hero__subtitle">{{ subtitle }}</p>
        </div>
        <div v-if="$slots.meta" class="page-hero__meta">
          <slot name="meta" />
        </div>
      </div>
      <div v-if="$slots.default" class="page-hero__body">
        <slot />
      </div>
    </div>

    <div v-if="$slots.actions" class="page-hero__actions">
      <slot name="actions" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  eyebrow?: string
  title: string
  subtitle?: string
  tone?: 'slate' | 'blue' | 'green' | 'gold'
}>()

const heroClass = computed(() => `page-hero--${props.tone || 'slate'}`)
</script>

<style scoped>
.page-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 28px;
  border-radius: 22px;
  color: #fff;
  box-shadow: 0 20px 48px rgba(15, 23, 42, 0.16);
}

.page-hero--slate {
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.22), transparent 34%),
    linear-gradient(135deg, #16324a 0%, #244c66 42%, #2f6b6f 100%);
}

.page-hero--blue {
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.22), transparent 34%),
    linear-gradient(135deg, #213874 0%, #3556b9 48%, #4f7cff 100%);
}

.page-hero--green {
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.22), transparent 34%),
    linear-gradient(135deg, #114232 0%, #1c6a51 50%, #2a8b74 100%);
}

.page-hero--gold {
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.22), transparent 34%),
    linear-gradient(135deg, #6d4600 0%, #946200 50%, #b9800d 100%);
}

.page-hero__copy {
  max-width: 820px;
}

.page-hero__eyebrow {
  margin: 0 0 10px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  color: rgba(255, 255, 255, 0.74);
}

.page-hero__title-row {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}

.page-hero__title {
  margin: 0;
  font-size: 28px;
  line-height: 1.12;
}

.page-hero__subtitle {
  margin: 10px 0 0;
  max-width: 640px;
  font-size: 14px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.84);
}

.page-hero__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.page-hero__body {
  margin-top: 14px;
}

.page-hero__actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .page-hero {
    padding: 20px;
    border-radius: 18px;
    flex-direction: column;
    align-items: stretch;
  }

  .page-hero__title {
    font-size: 24px;
  }

  .page-hero__actions :deep(.el-button) {
    flex: 1;
    min-width: 0;
  }
}
</style>
