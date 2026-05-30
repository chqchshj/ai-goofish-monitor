<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { GetSellerAggregationResponse } from '@/api/results'

interface Props {
  aggregation: GetSellerAggregationResponse | null
}

interface Emits {
  (e: 'select-seller', sellerNickname: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const { t } = useI18n()

const DEFAULT_VISIBLE = 6

const isExpanded = ref(false)

const showToggle = computed(() => {
  return (props.aggregation?.sellers?.length ?? 0) > DEFAULT_VISIBLE
})

const visibleSellers = computed(() => {
  const sellers = props.aggregation?.sellers ?? []
  if (isExpanded.value || sellers.length <= DEFAULT_VISIBLE) {
    return sellers
  }
  return sellers.slice(0, DEFAULT_VISIBLE)
})

function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

function handleSellerClick(nickname: string) {
  emit('select-seller', nickname)
}
</script>

<template>
  <div
    v-if="aggregation && aggregation.total_sellers > 0"
    class="app-surface mb-6 p-4 sm:p-5"
  >
    <div class="flex items-center justify-between mb-3">
      <h2 class="text-sm font-semibold text-slate-600">
        {{ t('results.sellers.title', { count: aggregation.total_sellers }) }}
      </h2>
      <div class="flex items-center gap-2">
        <span class="text-xs text-slate-400">
          {{ t('results.sellers.totalItems', { count: aggregation.total_items }) }}
        </span>
        <button
          v-if="showToggle"
          type="button"
          class="text-xs text-primary hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 rounded"
          @click="toggleExpand"
        >
          {{ isExpanded ? t('results.sellers.showLess') : t('results.sellers.showAll') }}
        </button>
      </div>
    </div>

    <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="seller in visibleSellers"
        :key="seller.seller_nickname"
        class="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 hover:border-slate-300 transition-colors cursor-pointer"
        @click="handleSellerClick(seller.seller_nickname)"
      >
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-slate-800 truncate">
              {{ seller.seller_nickname }}
            </span>
            <span
              v-if="seller.recommended_count > 0"
              class="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-700"
            >
              {{ t('results.sellers.recommended', { count: seller.recommended_count }) }}
            </span>
          </div>

          <div
            v-if="seller.personal_seller_summary"
            class="mt-0.5 text-xs text-slate-500 truncate"
          >
            {{ seller.personal_seller_summary }}
          </div>

          <div class="mt-1 flex items-center gap-3 text-xs text-slate-400">
            <span>{{ t('results.sellers.itemCount', { count: seller.item_count }) }}</span>
            <span v-if="seller.min_price != null">
              ¥{{ seller.min_price }}{{ seller.max_price !== seller.min_price ? ` - ¥${seller.max_price}` : '' }}
            </span>
          </div>
        </div>

        <div class="text-right shrink-0">
          <div class="text-xs text-slate-400">
            {{ seller.latest_crawl_time ? seller.latest_crawl_time.slice(0, 16).replace('T', ' ') : '' }}
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showToggle && !isExpanded"
      class="mt-2 text-center"
    >
      <span class="text-xs text-slate-400">
        {{ t('results.sellers.moreHidden', { count: aggregation.total_sellers - DEFAULT_VISIBLE }) }}
      </span>
    </div>
  </div>
</template>
