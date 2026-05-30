<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import type { ResultSort } from '@/api/results'

interface FileOption {
  value: string
  label: string
  taskName?: string
}

interface Props {
  files: string[]
  fileOptions?: FileOption[]
  selectedFile: string | null
  aiRecommendedOnly: boolean
  keywordRecommendedOnly: boolean
  includeHidden: boolean
  yhbOnly: boolean
  freeShippingOnly: boolean
  personalSellerOnly: boolean
  sort: ResultSort
  isLoading: boolean
  isReady: boolean
}

const props = defineProps<Props>()
const { t } = useI18n()

const options = computed(() => {
  if (!props.isReady) {
    return []
  }
  if (props.fileOptions && props.fileOptions.length > 0) {
    return props.fileOptions
  }
  return props.files.map((file) => ({ value: file, label: file }))
})

const selectedLabel = computed(() => {
  if (!props.isReady) return t('results.filters.loadingTaskNames')
  if (options.value.length === 0) return t('results.filters.noResults')
  if (!props.selectedFile) return t('results.filters.chooseResult')
  const match = options.value.find((option) => option.value === props.selectedFile)
  return match ? match.label : t('results.filters.taskNameLabel', { task: t('common.unnamed') })
})

const labelClass = computed(() => {
  const classes = ['transition-opacity', 'duration-200']
  if (!props.isReady || !props.selectedFile || options.value.length === 0) {
    classes.push('text-muted-foreground')
  }
  classes.push(props.isReady ? 'opacity-100' : 'opacity-70')
  return classes.join(' ')
})

const isSelectDisabled = computed(() => !props.isReady || options.value.length === 0)

const emit = defineEmits<{
  (e: 'update:selectedFile', value: string): void
  (e: 'update:aiRecommendedOnly', value: boolean): void
  (e: 'update:keywordRecommendedOnly', value: boolean): void
  (e: 'update:includeHidden', value: boolean): void
  (e: 'update:yhbOnly', value: boolean): void
  (e: 'update:freeShippingOnly', value: boolean): void
  (e: 'update:personalSellerOnly', value: boolean): void
  (e: 'update:sort', value: ResultSort): void
  (e: 'refresh'): void
  (e: 'export'): void
  (e: 'delete'): void
  (e: 'manage-blacklist'): void
}>()

function handleToggleAiRecommended(value: boolean) {
  emit('update:aiRecommendedOnly', value)
  if (value) {
    emit('update:keywordRecommendedOnly', false)
  }
}

function handleToggleKeywordRecommended(value: boolean) {
  emit('update:keywordRecommendedOnly', value)
  if (value) {
    emit('update:aiRecommendedOnly', false)
  }
}
</script>

<template>
  <div class="app-surface mb-6 p-4 sm:p-5">
    <div class="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <div class="space-y-2">
        <Label class="text-xs font-semibold text-slate-500">{{ t('results.title') }}</Label>
        <Select
          :model-value="props.selectedFile || undefined"
          @update:model-value="(value) => emit('update:selectedFile', value as string)"
        >
          <SelectTrigger class="w-full" :disabled="isSelectDisabled">
            <span :class="labelClass">
              {{ selectedLabel }}
            </span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="option in options" :key="option.value" :value="option.value">
              {{ option.label }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div class="space-y-2">
        <Label class="text-xs font-semibold text-slate-500">{{ t('results.filters.sortByCrawlTime') }}</Label>
        <Select
          :model-value="props.sort"
          @update:model-value="(value) => emit('update:sort', value as ResultSort)"
        >
          <SelectTrigger class="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="discovered_desc">{{ t('results.filters.sortByCrawlTime') }} · {{ t('results.filters.desc') }}</SelectItem>
            <SelectItem value="discovered_asc">{{ t('results.filters.sortByCrawlTime') }} · {{ t('results.filters.asc') }}</SelectItem>
            <SelectItem value="publish_desc">{{ t('results.filters.sortByPublishTime') }} · {{ t('results.filters.desc') }}</SelectItem>
            <SelectItem value="publish_asc">{{ t('results.filters.sortByPublishTime') }} · {{ t('results.filters.asc') }}</SelectItem>
            <SelectItem value="price_desc">{{ t('results.filters.sortByPrice') }} · {{ t('results.filters.desc') }}</SelectItem>
            <SelectItem value="price_asc">{{ t('results.filters.sortByPrice') }} · {{ t('results.filters.asc') }}</SelectItem>
            <SelectItem value="keyword_hit_desc">{{ t('results.filters.sortByKeywordHits') }} · {{ t('results.filters.desc') }}</SelectItem>
            <SelectItem value="keyword_hit_asc">{{ t('results.filters.sortByKeywordHits') }} · {{ t('results.filters.asc') }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>

    <div class="mt-4 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
      <div class="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <div class="flex items-center space-x-2">
          <Checkbox
            id="ai-recommended-only"
            :model-value="props.aiRecommendedOnly"
            @update:modelValue="(value) => handleToggleAiRecommended(value === true)"
          />
          <Label for="ai-recommended-only" class="cursor-pointer">{{ t('results.filters.aiOnly') }}</Label>
        </div>

        <div class="flex items-center space-x-2">
          <Checkbox
            id="keyword-recommended-only"
            :model-value="props.keywordRecommendedOnly"
            @update:modelValue="(value) => handleToggleKeywordRecommended(value === true)"
          />
          <Label for="keyword-recommended-only" class="cursor-pointer">{{ t('results.filters.keywordOnly') }}</Label>
        </div>

        <div class="flex items-center space-x-2">
          <Checkbox
            id="include-hidden"
            :model-value="props.includeHidden"
            @update:modelValue="(value) => emit('update:includeHidden', value === true)"
          />
          <Label for="include-hidden" class="cursor-pointer">{{ t('results.filters.includeHidden') }}</Label>
        </div>

        <div class="flex items-center space-x-2">
          <Checkbox
            id="yhb-only"
            :model-value="props.yhbOnly"
            @update:modelValue="(value) => emit('update:yhbOnly', value === true)"
          />
          <Label for="yhb-only" class="cursor-pointer">{{ t('results.filters.yhbOnly') }}</Label>
        </div>

        <div class="flex items-center space-x-2">
          <Checkbox
            id="free-shipping-only"
            :model-value="props.freeShippingOnly"
            @update:modelValue="(value) => emit('update:freeShippingOnly', value === true)"
          />
          <Label for="free-shipping-only" class="cursor-pointer">{{ t('results.filters.freeShippingOnly') }}</Label>
        </div>

        <div class="flex items-center space-x-2">
          <Checkbox
            id="personal-seller-only"
            :model-value="props.personalSellerOnly"
            @update:modelValue="(value) => emit('update:personalSellerOnly', value === true)"
          />
          <Label for="personal-seller-only" class="cursor-pointer">{{ t('results.filters.personalSellerOnly') }}</Label>
        </div>
      </div>

      <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap lg:justify-end">
        <Button @click="emit('refresh')" :disabled="props.isLoading">
          {{ t('common.refresh') }}
        </Button>

        <Button
          variant="outline"
          @click="emit('manage-blacklist')"
          :disabled="props.isLoading || !props.selectedFile"
        >
          {{ t('results.filters.manageBlacklist') }}
        </Button>

        <Button
          variant="outline"
          @click="emit('export')"
          :disabled="props.isLoading || !props.selectedFile"
        >
          {{ t('results.filters.exportCsv') }}
        </Button>

        <Button
          variant="destructive"
          @click="emit('delete')"
          :disabled="props.isLoading || !props.selectedFile"
        >
          {{ t('results.filters.deleteResult') }}
        </Button>
      </div>
    </div>
  </div>
</template>
