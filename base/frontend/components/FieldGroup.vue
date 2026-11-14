<template>
  <fieldset class="field-group">
    <slot />
  </fieldset>
</template>

<style scoped>
/* A fieldset is at least as wide as its widest control unless told otherwise, which would push a narrow window wider
   than the screen. */
.field-group {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
</style>
