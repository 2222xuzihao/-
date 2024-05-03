
 class SwinTransformer(nn.Module):
        r""" Swin Transformer
            A PyTorch impl of : `Swin Transformer: Hierarchical Vision Transformer using Shifted Windows`  -
              https://arxiv.org/pdf/2103.14030

        Args:
            patch_size (int | tuple(int)): Patch size. Default: 4
            in_chans (int): Number of input image channels. Default: 3
            num_classes (int): Number of classes for classification head. Default: 1000
            embed_dim (int): Patch embedding dimension. Default: 96
            depths (tuple(int)): Depth of each Swin Transformer layer.
            num_heads (tuple(int)): Number of attention heads in different layers.
            window_size (int): Window size. Default: 7
            mlp_ratio (float): Ratio of mlp hidden dim to embedding dim. Default: 4
            qkv_bias (bool): If True, add a learnable bias to query, key, value. Default: True
            drop_rate (float): Dropout rate. Default: 0
            attn_drop_rate (float): Attention dropout rate. Default: 0
            drop_path_rate (float): Stochastic depth rate. Default: 0.1
            norm_layer (nn.Module): Normalization layer. Default: nn.LayerNorm.
            patch_norm (bool): If True, add normalization after patch embedding. Default: True
            use_checkpoint (bool): Whether to use checkpointing to save memory. Default: False
        """

        # in_chans图像的深度
        # enmbed_dim为C  depth：swin-transformer重复的次数  num_heads为结构中head数量  window_size为win.sz7×7
        # mlp_ratio为mlp翻几倍  drop_rate在patchembed  drop_path rate是在swin-transformer里的，从0递增到0.1
        def __init__(self, patch_size=4, in_chans=3, num_classes=1000,
                     embed_dim=96, depths=(2, 2, 6, 2), num_heads=(3, 6, 12, 24),
                     window_size=7, mlp_ratio=4., qkv_bias=True,
                     drop_rate=0., attn_drop_rate=0., drop_path_rate=0.1,
                     norm_layer=nn.LayerNorm, patch_norm=True,
                     use_checkpoint=False, **kwargs):
            super().__init__()

            self.num_classes = num_classes
            self.num_layers = len(depths)
            self.embed_dim = embed_dim
            self.patch_norm = patch_norm
            # stage4输出特征矩阵的channels
            self.num_features = int(embed_dim * 2 ** (self.num_layers - 1))  # stage4的swin-transformer
            self.mlp_ratio = mlp_ratio

            # split image into non-overlapping patches 划分为无重叠的
            self.patch_embed = PatchEmbed(
                patch_size=patch_size, in_c=in_chans, embed_dim=embed_dim,
                norm_layer=norm_layer if self.patch_norm else None)
            self.pos_drop = nn.Dropout(p=drop_rate)

            # stochastic depth
            dpr = [x.item() for x in torch.linspace(0, drop_path_rate, sum(depths))]  # stochastic depth decay rule
            # 从0升高到drop_path_rate
            # build layers
            self.layers = nn.ModuleList()
            for i_layer in range(self.num_layers):
                # 注意这里构建的stage和论文图中有些差异
                # 这里的stage不包含该stage的patch_merging层，包含的是下个stage的
                layers = BasicLayer(dim=int(embed_dim * 2 ** i_layer),
                                    depth=depths[i_layer],
                                    num_heads=num_heads[i_layer],
                                    window_size=window_size,
                                    mlp_ratio=self.mlp_ratio,
                                    qkv_bias=qkv_bias,
                                    drop=drop_rate,
                                    attn_drop=attn_drop_rate,
                                    drop_path=dpr[sum(depths[:i_layer]):sum(depths[:i_layer + 1])],
                                    norm_layer=norm_layer,
                                    downsample=PatchMerging if (i_layer < self.num_layers - 1) else None,
                                    use_checkpoint=use_checkpoint)
                self.layers.append(layers)

            self.norm = norm_layer(self.num_features)
            self.avgpool = nn.AdaptiveAvgPool1d(1)  # 自适应全局平均池化，高、宽 1×1
            self.head = nn.Linear(self.num_features, num_classes) if num_classes > 0 else nn.Identity()

            self.apply(self._init_weights)

        def _init_weights(self, m):
            if isinstance(m, nn.Linear):
                nn.init.trunc_normal_(m.weight, std=.02)
                if isinstance(m, nn.Linear) and m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.LayerNorm):
                nn.init.constant_(m.bias, 0)
                nn.init.constant_(m.weight, 1.0)

        def forward(self, x):
            # x: [B, L, C]
            x, H, W = self.patch_embed(x)  # 下采样四倍
            x = self.pos_drop(x)

            for layer in self.layers:  # 遍历stage
                x, H, W = layer(x, H, W)

            x = self.norm(x)  # [B, L, C]  # stage4后加layer normalization
            x = self.avgpool(x.transpose(1, 2))  # [B, C, 1] L和C调换，再自适应池化
            x = torch.flatten(x, 1)
            x = self.head(x)  # 全连接层
            return x

