// Files › the tree of folders (BASE-G82, BASE-G85; the old hub's ok-file-manager tree): every folder of the business
// under «Files», the open one marked, a tap opens it, and a file or folder dragged from the list drops on one to move
// there (only where the person may move, and never onto the folder dragged itself).
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import type { FileFolder } from '../operations';
import FileTree from './FileTree.vue';

const TREE: FileFolder[] = [
  { path: 'Contratos', name: 'Contratos', children: [] },
  { path: 'Facturas', name: 'Facturas', children: [{ path: 'Facturas/2026', name: '2026', children: [] }] },
];

function tree(props: Partial<{ selected: string; droppable: boolean; dragging: string | null }> = {}) {
  return mount(FileTree, {
    props: { nodes: TREE, selected: '', droppable: false, dragging: null, ...props },
    global: { stubs: { HubIcon: true } },
  });
}

const node = (wrapper: ReturnType<typeof tree>, path: string) => wrapper.find(`[data-folder="${path}"]`);

describe('FileTree', () => {
  it('paints every folder, nested, and marks the open one', () => {
    const wrapper = tree({ selected: 'Facturas/2026' });
    expect(wrapper.findAll('[data-folder]').map((item) => item.text())).toEqual(['Contratos', 'Facturas', '2026']);
    expect(node(wrapper, 'Facturas/2026').attributes('aria-current')).toBe('true');
    expect(node(wrapper, 'Facturas').attributes('aria-current')).toBeUndefined();
  });

  it('a tap opens the folder', async () => {
    const wrapper = tree();
    await node(wrapper, 'Facturas/2026').trigger('click');
    expect(wrapper.emitted('select')).toEqual([['Facturas/2026']]);
  });

  it('a dragged file drops on a folder to move there, where the person may move', async () => {
    const wrapper = tree({ droppable: true, dragging: 'a.pdf' });
    await node(wrapper, 'Contratos').trigger('dragover');
    expect(node(wrapper, 'Contratos').classes()).toContain('file-tree-target');
    await node(wrapper, 'Contratos').trigger('drop');
    expect(wrapper.emitted('drop')).toEqual([['Contratos']]);
  });

  it('nothing drops where the person may not move, nor a folder onto itself or inside itself', async () => {
    const locked = tree({ droppable: false, dragging: 'a.pdf' });
    await node(locked, 'Contratos').trigger('drop');
    expect(locked.emitted('drop')).toBeUndefined();
    const own = tree({ droppable: true, dragging: 'Facturas' });
    await node(own, 'Facturas').trigger('drop');
    await node(own, 'Facturas/2026').trigger('drop');
    expect(own.emitted('drop')).toBeUndefined();
  });
});
