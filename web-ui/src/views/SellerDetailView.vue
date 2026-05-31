<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getSellerDetail, getSellerItems, updateSellerTracking, deleteSellerTracking } from '@/api/sellers'
import type { SellerDetail, SellerItemsResponse } from '@/api/sellers'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toast'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const sellerKey = computed(() => route.params.sellerKey as string)
const resultFilename = computed(() => (route.query.result_filename as string) || '')

const seller = ref<SellerDetail | null>(null)
const items = ref<SellerItemsResponse | null>(null)
const isLoading = ref(false)
const isItemsLoading = ref(false)
const error = ref<Error | null>(null)
const itemsPage = ref(1)
const itemsLimit = 20

// Editing state
const isEditing = ref(false)
const editNotes = ref('')
const editStatus = ref('')
const editTags = ref('')
const isSaving = ref(false)

// Delete dialog
const isDeleteDialogOpen = ref(false)
const isDeleting = ref(false)

const statusOptions = ['normal', 'favorite', 'ignored', 'blacklisted']

async function fetchSellerDetail() {
  if (!sellerKey.value || !resultFilename.value) return
  isLoading.value = true
  error.value = null
  try {
    seller.value = await getSellerDetail(sellerKey.value, resultFilename.value)
  } catch (e) {
    error.value = e as Error
  } finally {
    isLoading.value = false
  }
}

async function fetchItems() {
  if (!sellerKey.value || !resultFilename.value) return
  isItemsLoading.value = true
  try {
    items.value = await getSellerItems(sellerKey.value, resultFilename.value, itemsPage.value, itemsLimit)
  } catch (e) {
    toast({ title: t('sellerDetail.itemsLoadFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isItemsLoading.value = false
  }
}

function startEditing() {
  if (!seller.value) return
  editNotes.value = seller.value.notes
  editStatus.value = seller.value.status
  editTags.value = seller.value.tags.join(', ')
  isEditing.value = true
}

function cancelEditing() {
  isEditing.value = false
}

async function saveTracking() {
  if (!seller.value) return
  isSaving.value = true
  try {
    const tags = editTags.value
      .split(/[,，]/)
      .map((t) => t.trim())
      .filter(Boolean)
    await updateSellerTracking(sellerKey.value, {
      status: editStatus.value,
      notes: editNotes.value,
      tags,
    })
    // Refresh detail
    await fetchSellerDetail()
    isEditing.value = false
    toast({ title: t('sellerDetail.saveSuccess') })
  } catch (e) {
    toast({ title: t('sellerDetail.saveFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isSaving.value = false
  }
}

async function confirmDeleteTracking() {
  isDeleting.value = true
  try {
    await deleteSellerTracking(sellerKey.value)
    await fetchSellerDetail()
    isDeleteDialogOpen.value = false
    toast({ title: t('sellerDetail.deleteSuccess') })
  } catch (e) {
    toast({ title: t('sellerDetail.deleteFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isDeleting.value = false
  }
}

function goBack() {
  router.back()
}

function goToPage(page: number) {
  itemsPage.value = page
}

const totalPages = computed(() => {
  if (!items.value) return 0
  return Math.ceil(items.value.total / itemsLimit)
})

function statusColor(status: string) {
  switch (status) {
    case 'favorite': return 'bg-amber-100 text-amber-700'
    case 'ignored': return 'bg-slate-100 text-slate-500'
    case 'blacklisted': return 'bg-red-100 text-red-700'
    default: return 'bg-green-100 text-green-700'
  }
}

// Fetch on mount and when params change
watch([sellerKey, resultFilename], () => {
  fetchSellerDetail()
  itemsPage.value = 1
  fetchItems()
}, { immediate: true })

watch(itemsPage, () => {
  fetchItems()
})
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center gap-3 mb-6">
      <button
        type="button"
        class="text-slate-500 hover:text-slate-700 transition-colors"
        :aria-label="t('sellerDetail.back')"
        @click="goBack"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>
      <h1 class="text-2xl font-bold text-gray-800">
        {{ t('sellerDetail.title') }}
      </h1>
    </div>

    <!-- Error -->
    <div v-if="error" class="app-alert-error mb-4" role="alert">
      <strong class="font-bold">{{ t('common.error') }}</strong>
      <span class="block sm:inline">{{ error.message }}</span>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="text-center py-12 text-slate-500">
      {{ t('common.loading') }}
    </div>

    <!-- No result_filename -->
    <div v-else-if="!resultFilename" class="app-surface p-6 text-center text-slate-500">
      {{ t('sellerDetail.noResultFile') }}
    </div>

    <!-- Seller Detail -->
    <template v-else-if="seller">
      <!-- Summary Card -->
      <div class="app-surface p-5 mb-6">
        <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-3 mb-2">
              <h2 class="text-lg font-semibold text-slate-800 truncate">
                {{ seller.seller_nickname }}
              </h2>
              <span :class="['rounded px-2 py-0.5 text-xs font-medium', statusColor(seller.status)]">
                {{ t(`sellerDetail.status.${seller.status}`) }}
              </span>
            </div>

            <p v-if="seller.personal_seller_summary" class="text-sm text-slate-600 mb-3">
              {{ seller.personal_seller_summary }}
            </p>

            <div class="flex flex-wrap gap-4 text-sm text-slate-500">
              <span>{{ t('sellerDetail.itemCount', { count: seller.item_count }) }}</span>
              <span v-if="seller.recommended_count > 0">
                {{ t('sellerDetail.recommended', { count: seller.recommended_count }) }}
              </span>
              <span v-if="seller.min_price != null">
                ¥{{ seller.min_price }}{{ seller.max_price !== seller.min_price ? ` - ¥${seller.max_price}` : '' }}
              </span>
              <span v-if="seller.latest_crawl_time">
                {{ t('sellerDetail.lastCrawl') }}: {{ seller.latest_crawl_time.slice(0, 16).replace('T', ' ') }}
              </span>
            </div>
          </div>

          <div class="flex gap-2 shrink-0">
            <Button v-if="!isEditing" size="sm" variant="outline" @click="startEditing">
              {{ t('sellerDetail.edit') }}
            </Button>
            <Button v-if="!isEditing" size="sm" variant="outline" class="text-red-600 hover:text-red-700" @click="isDeleteDialogOpen = true">
              {{ t('sellerDetail.deleteTracking') }}
            </Button>
          </div>
        </div>

        <!-- Tags -->
        <div v-if="seller.tags.length > 0 && !isEditing" class="mt-3 flex flex-wrap gap-1.5">
          <span
            v-for="tag in seller.tags"
            :key="tag"
            class="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-600"
          >
            {{ tag }}
          </span>
        </div>

        <!-- Notes (read-only) -->
        <div v-if="seller.notes && !isEditing" class="mt-3 rounded-lg bg-slate-50 p-3">
          <p class="text-sm text-slate-600 whitespace-pre-wrap">{{ seller.notes }}</p>
        </div>

        <!-- Edit Form -->
        <div v-if="isEditing" class="mt-4 space-y-4 border-t border-slate-200 pt-4">
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">{{ t('sellerDetail.statusLabel') }}</label>
            <select
              v-model="editStatus"
              class="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            >
              <option v-for="opt in statusOptions" :key="opt" :value="opt">
                {{ t(`sellerDetail.status.${opt}`) }}
              </option>
            </select>
          </div>

          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">{{ t('sellerDetail.notesLabel') }}</label>
            <Textarea v-model="editNotes" class="min-h-[80px]" :placeholder="t('sellerDetail.notesPlaceholder')" />
          </div>

          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">{{ t('sellerDetail.tagsLabel') }}</label>
            <input
              v-model="editTags"
              type="text"
              class="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              :placeholder="t('sellerDetail.tagsPlaceholder')"
            />
          </div>

          <div class="flex gap-2">
            <Button size="sm" :disabled="isSaving" @click="saveTracking">
              {{ isSaving ? t('common.saving') : t('common.save') }}
            </Button>
            <Button size="sm" variant="outline" @click="cancelEditing">
              {{ t('common.cancel') }}
            </Button>
          </div>
        </div>
      </div>

      <!-- Items Section -->
      <div class="app-surface p-5">
        <h3 class="text-sm font-semibold text-slate-600 mb-4">
          {{ t('sellerDetail.itemsTitle', { total: items?.total ?? 0 }) }}
        </h3>

        <div v-if="isItemsLoading" class="text-center py-8 text-slate-500">
          {{ t('common.loading') }}
        </div>

        <div v-else-if="items && items.items.length > 0" class="space-y-3">
          <div
            v-for="item in items.items"
            :key="item.item_id || item.id"
            class="flex gap-3 rounded-lg border border-slate-200 p-3 hover:border-slate-300 transition-colors"
          >
            <img
              v-if="item.pic_url || item.image_url"
              :src="item.pic_url || item.image_url"
              :alt="item.title"
              class="w-16 h-16 rounded object-cover shrink-0"
              loading="lazy"
            />
            <div class="flex-1 min-w-0">
              <a
                v-if="item.detail_url"
                :href="item.detail_url"
                target="_blank"
                rel="noopener noreferrer"
                class="text-sm font-medium text-slate-800 hover:text-primary line-clamp-2"
              >
                {{ item.title }}
              </a>
              <p v-else class="text-sm font-medium text-slate-800 line-clamp-2">{{ item.title }}</p>

              <div class="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                <span v-if="item.price != null" class="font-medium text-slate-700">¥{{ item.price }}</span>
                <span v-if="item.crawl_time">{{ item.crawl_time.slice(0, 16).replace('T', ' ') }}</span>
                <span
                  v-if="item.is_recommended"
                  class="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-700"
                >
                  {{ t('sellerDetail.itemRecommended') }}
                </span>
              </div>
            </div>
          </div>

          <!-- Pagination -->
          <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 pt-4">
            <Button
              size="sm"
              variant="outline"
              :disabled="itemsPage <= 1"
              @click="goToPage(itemsPage - 1)"
            >
              {{ t('sellerDetail.prevPage') }}
            </Button>
            <span class="text-sm text-slate-500">
              {{ itemsPage }} / {{ totalPages }}
            </span>
            <Button
              size="sm"
              variant="outline"
              :disabled="itemsPage >= totalPages"
              @click="goToPage(itemsPage + 1)"
            >
              {{ t('sellerDetail.nextPage') }}
            </Button>
          </div>
        </div>

        <div v-else class="text-center py-8 text-slate-400">
          {{ t('sellerDetail.noItems') }}
        </div>
      </div>
    </template>

    <!-- Delete Tracking Dialog -->
    <Dialog v-model:open="isDeleteDialogOpen">
      <DialogContent class="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{{ t('sellerDetail.deleteDialogTitle') }}</DialogTitle>
          <DialogDescription>
            {{ t('sellerDetail.deleteDialogDescription', { seller: seller?.seller_nickname }) }}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="isDeleteDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button variant="destructive" :disabled="isDeleting" @click="confirmDeleteTracking">
            {{ isDeleting ? t('common.loading') : t('common.delete') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
