<script setup lang="ts">
// The guide (WORKBOOK FLOW-F08; the old module's `erp-flows-guide`): «How automations work» in five
// parts — what one is, the first one step by step, why permissions need a yes, how to know it
// worked, and what it cannot do yet —, with its texts inside the app. «Back to the automations» returns.
import { AppPage, HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { useRouter } from 'vue-router';

const router = useRouter();
const FIRST_STEPS = 5;
const LIMITS = 4;
</script>

<template>
  <AppPage
    :title="$t('flow.guide.title')"
    back-href="/flow/automations"
    content-layout="detail"
  >
    <div class="flow-guide">
      <section data-testid="flow-guide-section-what">
        <h2>{{ $t('flow.guide.what.title') }}</h2>
        <p>{{ $t('flow.guide.what.body') }}</p>
      </section>
      <section data-testid="flow-guide-section-first">
        <h2>{{ $t('flow.guide.first.title') }}</h2>
        <ol>
          <li
            v-for="n in FIRST_STEPS"
            :key="n"
          >
            {{ $t(`flow.guide.first.steps.${n - 1}`) }}
          </li>
        </ol>
      </section>
      <section data-testid="flow-guide-section-permissions">
        <h2>{{ $t('flow.guide.permissions.title') }}</h2>
        <p>{{ $t('flow.guide.permissions.body') }}</p>
      </section>
      <section data-testid="flow-guide-section-worked">
        <h2>{{ $t('flow.guide.worked.title') }}</h2>
        <p>{{ $t('flow.guide.worked.body') }}</p>
      </section>
      <section data-testid="flow-guide-section-limits">
        <h2>{{ $t('flow.guide.limits.title') }}</h2>
        <ul>
          <li
            v-for="n in LIMITS"
            :key="n"
          >
            {{ $t(`flow.guide.limits.items.${n - 1}`) }}
          </li>
        </ul>
      </section>
      <IonButton
        mode="md"
        fill="outline"
        data-testid="flow-guide-back"
        @click="router.push('/flow/automations')"
      >
        <HubIcon name="ion:arrow-back-outline" />{{ $t('flow.guide.back') }}
      </IonButton>
    </div>
  </AppPage>
</template>

<style scoped>
.flow-guide {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 44rem;
  margin: 0 auto;
}
.flow-guide h2 {
  margin: 0 0 0.35rem;
  font-size: 1.05rem;
}
.flow-guide p,
.flow-guide ol,
.flow-guide ul {
  margin: 0;
  line-height: 1.5;
}
.flow-guide > ion-button {
  align-self: flex-start;
}
</style>
